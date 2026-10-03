"""Generate one synthetic interactive preview with real Sonnet; publish only saved Git source."""
from __future__ import annotations

import json
import shutil
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[4]
sys.path.insert(0, str(ROOT / "tools" / "support_agent"))
from support_agent.config import Config  # noqa: E402
from support_agent.llm import LlmRouter  # noqa: E402
from support_agent.publish_mockup import publish  # noqa: E402
from support_agent.store import Store  # noqa: E402


def main() -> None:
    target = Path(__file__).parent / "preview-smoke"
    report = Path(__file__).with_suffix(".json")
    if sys.argv[1] == "generate":
        work = ROOT / ".bot-audit-20261003" / "native-fixture"
        work.mkdir(parents=True, exist_ok=True)
        cfg = Config(repo=str(work), state_dir=str(work / "preview-state"))
        store = Store(work / "preview.db")
        llm = LlmRouter(cfg, store)
        result = llm.agent_turn(
            "Ты Sonnet, исполняешь техническую проверку интерактивных макетов WMS. "
            "Создай preview/index.html внутри текущего рабочего каталога. Один автономный HTML, "
            "без внешних ресурсов. Покажи простой учебный экран задачи: заголовок 'Проверка макета WMS', "
            "пометка 'Тестовые данные', две строки ячеек A-01 и A-02, кнопка 'Показать детали', "
            "которая действительно раскрывает и скрывает блок с текстом 'Интерактивность работает'. "
            "Макет должен помещаться на телефоне. Только синтетические данные. "
            "Это проверка транспорта, не правка WMS; не запускай других агентов, не читай проект. "
            "Не делай коммит, не публикуй и не отправляй сообщения. В конце дай путь к файлу.",
            session_key="preview-smoke", model="sonnet", provider="claude", mode="write",
            cwd=str(work), timeout=300,
        )
        source = work / "preview" / "index.html"
        assert source.is_file(), result.text
        target.mkdir(exist_ok=True)
        shutil.copyfile(source, target / "index.html")
        report.write_text(json.dumps({"model": result.model, "provider": result.cli,
                                     "reply": result.text, "source": str(target.relative_to(ROOT)),
                                     "scope": "synthetic preview; no client data"},
                                    ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
        print(json.dumps({"generated": str(target)}), flush=True)
    elif sys.argv[1] == "publish":
        tracked = str((target / "index.html").relative_to(ROOT))
        subprocess.run(["git", "ls-files", "--error-unmatch", tracked], cwd=ROOT,
                       capture_output=True, check=True)
        assert not subprocess.check_output(["git", "status", "--porcelain", "--", tracked], cwd=ROOT)
        sha = subprocess.check_output(["git", "rev-parse", "HEAD"], cwd=ROOT, text=True).strip()
        url = publish(target, public_id="6412026100300000000000001")
        evidence = json.loads(report.read_text(encoding="utf-8"))
        evidence.update(source_sha=sha, public_url=url, verified="HTTP 200 and exact index.html SHA256")
        report.write_text(json.dumps(evidence, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
        print(json.dumps({"published": url, "source_sha": sha}), flush=True)
    else:
        raise SystemExit("use generate or publish")


if __name__ == "__main__":
    main()
