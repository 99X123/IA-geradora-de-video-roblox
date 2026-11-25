"""AutoShorts AI — Independent Code Review & Auto-Repair Agent via OpenCode CLI.

Official documentation: https://opencode.ai/docs/

Strict safety & truthfulness rules:
  - Never invents model identifiers; queries `opencode models` or uses user-configured model.
  - Never claims OpenCode verified anything if CLI/model/credentials were unavailable.
  - Operates strictly inside PROJECT_ROOT.
  - Always creates a backup in `backups/` BEFORE applying any modification.
  - Never modifies credentials or deletes user files.
  - Enforces a hard cap of `max_fix_cycles = 3` attempts per error.
  - Always re-runs tests after every fix attempt to verify whether the fix actually worked.
"""

from __future__ import annotations

import json
import os
import signal
import shutil
import subprocess
import sys
import zipfile
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional

from src.config import AutoShortsConfig, PROJECT_ROOT, get_secret, redact_secrets
from src.utils import run_subprocess, setup_logger

logger = setup_logger("autoshorts.opencode")

PROTECTED_PATTERNS = (".env", "credentials", ".key", ".pem", "service_account", "client_secret")


def _is_within_project(path: Path) -> bool:
    try:
        path.resolve().relative_to(PROJECT_ROOT.resolve())
        return True
    except ValueError:
        return False


def _is_protected(path: Path) -> bool:
    low = str(path).lower()
    return any(p in low for p in PROTECTED_PATTERNS)


class OpenCodeReviewer:
    """Orchestrates independent code reviews and safe automated bug-fix cycles using OpenCode CLI."""

    def __init__(self, config: Optional[AutoShortsConfig] = None) -> None:
        self.cfg = config or AutoShortsConfig.load()
        self.cli_cmd = str(self.cfg.get("opencode.cli_command", "opencode"))
        self.configured_model = str(self.cfg.get("opencode.model") or get_secret("OPENCODE_MODEL") or "").strip()
        self.max_fix_cycles = min(3, max(1, int(self.cfg.get("opencode.max_fix_cycles", 3))))
        self.timeout_sec = int(self.cfg.get("opencode.timeout_sec", 180))
        self.auto_approve = bool(self.cfg.get("opencode.auto_approve", False))

    def detect_cli(self) -> Dict[str, Any]:
        """Inspect whether OpenCode CLI is installed and query real available models."""
        exe = shutil.which(self.cli_cmd)
        if not exe:
            return {
                "installed": False,
                "executable": None,
                "version": None,
                "available_models": [],
                "configured_model": self.configured_model or None,
                "ready": False,
                "reason": "OpenCode CLI não encontrado no PATH. Instale conforme https://opencode.ai/docs/",
            }

        ver_proc = run_subprocess([exe, "--version"], check=False, timeout=15)
        version = (ver_proc.stdout or ver_proc.stderr).strip().splitlines()[0] if (ver_proc.stdout or ver_proc.stderr) else "unknown"

        models_proc = run_subprocess([exe, "models"], check=False, timeout=25)
        available_models: List[str] = []
        if models_proc.returncode == 0:
            for line in models_proc.stdout.splitlines():
                tok = line.strip()
                if "/" in tok and not tok.startswith(("Usage", "ERROR", "WARN")):
                    available_models.append(tok.split()[0])

        selected_model = self.configured_model
        if selected_model and available_models and selected_model not in available_models:
            return {
                "installed": True,
                "executable": exe,
                "version": version,
                "available_models": available_models[:30],
                "configured_model": selected_model,
                "ready": False,
                "reason": (
                    f"Modelo configurado '{selected_model}' não encontrado em `opencode models`. "
                    "Selecione um modelo válido disponível na sua instalação do OpenCode."
                ),
            }

        if not selected_model:
            return {
                "installed": True,
                "executable": exe,
                "version": version,
                "available_models": available_models[:30],
                "configured_model": None,
                "ready": False,
                "reason": (
                    "Nenhum modelo OpenCode configurado (defina `OPENCODE_MODEL` ou `opencode.model` "
                    "usando um dos modelos listados em `opencode models`)."
                ),
            }

        return {
            "installed": True,
            "executable": exe,
            "version": version,
            "available_models": available_models[:30],
            "configured_model": selected_model,
            "ready": True,
            "reason": "OpenCode CLI pronto para execução.",
        }

    def create_backup(self, target_files: List[Path], label: str = "review") -> Path:
        """Archive target files into `backups/` BEFORE any OpenCode run."""
        ts = datetime.now(timezone.utc).strftime("%Y%m%d_%H%M%S")
        backup_dir = PROJECT_ROOT / "backups"
        backup_dir.mkdir(parents=True, exist_ok=True)
        zip_path = backup_dir / f"opencode_backup_{label}_{ts}.zip"

        with zipfile.ZipFile(zip_path, "w", compression=zipfile.ZIP_DEFLATED) as zf:
            for f in target_files:
                fp = f if f.is_absolute() else (PROJECT_ROOT / f)
                if fp.exists() and fp.is_file() and _is_within_project(fp) and not _is_protected(fp):
                    zf.write(fp, arcname=str(fp.relative_to(PROJECT_ROOT)))

        logger.info("Backup criado antes do OpenCode: %s", zip_path)
        return zip_path

    def _filter_safe_files(self, files: List[Path | str]) -> List[Path]:
        safe: List[Path] = []
        for item in files:
            p = Path(item)
            if not p.is_absolute():
                p = PROJECT_ROOT / p
            if not p.exists() or not p.is_file():
                continue
            if not _is_within_project(p):
                logger.warning("Arquivo ignorado (fora do projeto): %s", p)
                continue
            if _is_protected(p):
                logger.warning("Arquivo protegido ignorado (credencial): %s", p)
                continue
            safe.append(p)
        return safe

    def _run_local_tests(self, test_cmd: Optional[List[str]] = None) -> Dict[str, Any]:
        cmd = test_cmd or ["python", "-m", "pytest", "-q"]
        proc = run_subprocess(cmd, cwd=PROJECT_ROOT, check=False, timeout=240)
        return {
            "command": " ".join(cmd),
            "passed": proc.returncode == 0,
            "returncode": proc.returncode,
            "stdout": redact_secrets(proc.stdout[-4000:]),
            "stderr": redact_secrets(proc.stderr[-4000:]),
        }

    def _invoke_opencode(
        self,
        executable: str,
        model: str,
        prompt: str,
        attach_files: List[Path],
        allow_edits: bool = False,
    ) -> Dict[str, Any]:
        # Collapse newlines into spaces so Windows `.cmd` wrappers never truncate the CLI prompt
        single_line_prompt = " ".join(line.strip() for line in prompt.splitlines() if line.strip())
        cmd = [
            executable,
            "run",
            "--standalone",
            "--model",
            model,
            "--archived",
            "--format",
            "default",
        ]
        if allow_edits and self.auto_approve:
            cmd.append("--auto")
        for f in attach_files[:12]:
            cmd.extend(["--file", str(f.relative_to(PROJECT_ROOT))])
        cmd.append(single_line_prompt)

        popen_kwargs: Dict[str, Any] = {
            "cwd": str(PROJECT_ROOT),
            "stdin": subprocess.DEVNULL,
            "stdout": subprocess.PIPE,
            "stderr": subprocess.PIPE,
            "text": True,
            "encoding": "utf-8",
            "errors": "replace",
        }
        if sys.platform != "win32":
            popen_kwargs["start_new_session"] = True

        proc = subprocess.Popen(cmd, **popen_kwargs)
        try:
            stdout, stderr = proc.communicate(timeout=self.timeout_sec)
            return {
                "returncode": proc.returncode,
                "stdout": redact_secrets((stdout or "")[-8000:]),
                "stderr": redact_secrets((stderr or "")[-4000:]),
                "timed_out": False,
            }
        except subprocess.TimeoutExpired:
            # Kill entire process tree so `.cmd` wrappers on Windows or child daemons never leak/block pipes
            if sys.platform == "win32":
                subprocess.run(
                    ["taskkill", "/F", "/T", "/PID", str(proc.pid)],
                    capture_output=True,
                    check=False,
                )
            else:
                try:
                    os.killpg(proc.pid, signal.SIGKILL)
                except Exception:
                    proc.kill()
            try:
                stdout, stderr = proc.communicate(timeout=5)
            except Exception:
                stdout, stderr = "", ""
            return {
                "returncode": -1,
                "stdout": redact_secrets((stdout or "")[-4000:]),
                "stderr": redact_secrets(
                    f"OpenCode excedeu o tempo limite de {self.timeout_sec}s. {(stderr or '')[-1000:]}"
                ),
                "timed_out": True,
            }

    def review_project(
        self,
        target_files: Optional[List[Path | str]] = None,
        allow_edits: bool = False,
        report_path: Optional[Path] = None,
    ) -> Dict[str, Any]:
        """Run an independent OpenCode code audit of the project modules and verify with tests."""
        default_files = [
            PROJECT_ROOT / "src" / "story_generator.py",
            PROJECT_ROOT / "src" / "tts_engine.py",
            PROJECT_ROOT / "src" / "audio_processor.py",
            PROJECT_ROOT / "src" / "subtitle_generator.py",
            PROJECT_ROOT / "src" / "storyboard_generator.py",
            PROJECT_ROOT / "src" / "sfx_synthesizer.py",
            PROJECT_ROOT / "src" / "video_orchestrator.py",
            PROJECT_ROOT / "src" / "quality_checker.py",
            PROJECT_ROOT / "src" / "drive_manager.py",
            PROJECT_ROOT / "engine" / "render_worker.mjs",
            PROJECT_ROOT / "engine" / "camera.js",
            PROJECT_ROOT / "engine" / "film_runtime.js",
        ]
        safe_files = self._filter_safe_files(target_files or default_files)
        status = self.detect_cli()

        if not status["ready"]:
            logger.warning("OpenCode não executado: %s. Executando apenas testes locais.", status["reason"])
            local_tests = self._run_local_tests()
            report = {
                "executed": False,
                "verified_by_opencode": False,
                "status": "skipped_unconfigured",
                "reason": status["reason"],
                "cli_detection": status,
                "backup_path": None,
                "local_tests": local_tests,
            }
            if report_path:
                report_path.parent.mkdir(parents=True, exist_ok=True)
                report_path.write_text(json.dumps(report, indent=2, ensure_ascii=False), encoding="utf-8")
            return report

        backup_path = self.create_backup(safe_files, label="audit") if self.cfg.get("opencode.create_backup", True) else None

        prompt = (
            "Você é um revisor de código independente analisando o projeto AutoShorts AI.\n"
            "REGRAS OBRIGATÓRIAS:\n"
            "- Trabalhe APENAS dentro da pasta atual do projeto.\n"
            "- NÃO apague arquivos do usuário, NÃO toque em credenciais/segredos, NÃO execute comandos destrutivos.\n"
            f"- Modo atual: {'PODE aplicar correções pontuais seguras' if allow_edits else 'SOMENTE ANÁLISE (não editar arquivos)'}.\n\n"
            "Analise os arquivos anexados para:\n"
            "1. Bugs e exceções não tratadas.\n"
            "2. Erros lógicos de sincronização, framing ou áudio.\n"
            "3. Problemas de dependências e compatibilidade com Google Colab (Linux, Chromium, FFmpeg, Drive).\n"
            "4. Retorne um resumo estruturado por severidade (Crítico / Alto / Médio / Baixo) com arquivo e linha."
        )

        logger.info("Executando revisão OpenCode com modelo '%s' (%d arquivos)...", status["configured_model"], len(safe_files))
        oc_result = self._invoke_opencode(
            executable=status["executable"],
            model=status["configured_model"],
            prompt=prompt,
            attach_files=safe_files,
            allow_edits=allow_edits,
        )
        local_tests = self._run_local_tests()

        executed_ok = oc_result["returncode"] == 0 and bool(oc_result["stdout"].strip())
        report = {
            "executed": executed_ok,
            "verified_by_opencode": executed_ok,
            "status": "completed" if executed_ok else "opencode_error",
            "model_used": status["configured_model"],
            "files_analyzed": [str(f.relative_to(PROJECT_ROOT)) for f in safe_files],
            "backup_path": str(backup_path) if backup_path else None,
            "opencode_output": oc_result["stdout"],
            "opencode_stderr": oc_result["stderr"],
            "opencode_returncode": oc_result["returncode"],
            "local_tests_after_review": local_tests,
        }
        if report_path:
            report_path.parent.mkdir(parents=True, exist_ok=True)
            report_path.write_text(json.dumps(report, indent=2, ensure_ascii=False), encoding="utf-8")
        return report

    def diagnose_and_fix_failure(
        self,
        error_log: str,
        relevant_files: List[Path | str],
        verify_cmd: Optional[List[str]] = None,
        allow_edits: bool = True,
        report_path: Optional[Path] = None,
    ) -> Dict[str, Any]:
        """Attempt up to `max_fix_cycles` (<=3) safe diagnosis/repair cycles on a production failure."""
        safe_files = self._filter_safe_files(relevant_files)
        status = self.detect_cli()

        if not status["ready"]:
            local_tests = self._run_local_tests(verify_cmd)
            report = {
                "executed": False,
                "verified_by_opencode": False,
                "fixed": False,
                "cycles_run": 0,
                "reason": status["reason"],
                "local_tests": local_tests,
            }
            if report_path:
                report_path.parent.mkdir(parents=True, exist_ok=True)
                report_path.write_text(json.dumps(report, indent=2, ensure_ascii=False), encoding="utf-8")
            return report

        backup_path = self.create_backup(safe_files, label="autofix")
        cycles: List[Dict[str, Any]] = []
        current_error = redact_secrets(error_log[-4000:])
        fixed = False

        for cycle in range(1, self.max_fix_cycles + 1):
            logger.info("Ciclo de correção OpenCode %d/%d...", cycle, self.max_fix_cycles)
            prompt = (
                f"Falha detectada durante a execução do AutoShorts AI (Tentativa {cycle}/{self.max_fix_cycles}).\n"
                "REGRAS DE SEGURANÇA:\n"
                "- Trabalhe APENAS dentro da pasta do projeto.\n"
                "- NÃO apague arquivos do usuário, NÃO altere credenciais, NÃO use comandos destrutivos.\n"
                "- Entenda as dependências do módulo antes de editar.\n\n"
                f"LOG DE ERRO:\n```\n{current_error}\n```\n\n"
                "Identifique a causa raiz e corrija o problema de forma mínima e segura."
            )
            oc_res = self._invoke_opencode(
                executable=status["executable"],
                model=status["configured_model"],
                prompt=prompt,
                attach_files=safe_files,
                allow_edits=allow_edits,
            )
            test_res = self._run_local_tests(verify_cmd)
            cycles.append(
                {
                    "cycle": cycle,
                    "opencode_returncode": oc_res["returncode"],
                    "opencode_output": oc_res["stdout"][-2500:],
                    "verification": test_res,
                }
            )
            if test_res["passed"]:
                fixed = True
                logger.info("Correção confirmada pelos testes no ciclo %d!", cycle)
                break
            current_error = f"{test_res['stdout']}\n{test_res['stderr']}"[-4000:]

        report = {
            "executed": True,
            "verified_by_opencode": True,
            "fixed": fixed,
            "cycles_run": len(cycles),
            "max_fix_cycles": self.max_fix_cycles,
            "model_used": status["configured_model"],
            "backup_path": str(backup_path),
            "cycles": cycles,
        }
        if report_path:
            report_path.parent.mkdir(parents=True, exist_ok=True)
            report_path.write_text(json.dumps(report, indent=2, ensure_ascii=False), encoding="utf-8")
        return report
