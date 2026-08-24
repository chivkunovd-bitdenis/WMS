# GitHub Agentic Workflows

**Источник:** [Develop agentic workflows in GitHub Actions](https://docs.github.com/en/actions/tutorials/develop-agentic-workflows-in-github-actions), проверено 2026-08-24. **Класс:** E2 docs with generated executable workflow; `gh-aw` code is the needed E1 follow-up. **Граница:** repository automation compiled to GitHub Actions, not a full product-development process.

## Реальный declared flow

Автор пишет Markdown workflow and chooses coding agent; `gh aw` compiles it to a `.lock.yml` GitHub Actions workflow. Документация требует review and commit both source Markdown and generated lock file. Trigger запускает runner; agent получает repo context и выполняет instruction, например PR test review. GitHub Actions then supplies ordinary job status/log/permission boundary.

## Переходы/контракты

Machine: event trigger → compiled workflow job → action execution → job success/failure → PR/issue output. Model: interpretation/edit/review inside agent. Markdown is a prompt artifact; locked YAML is reviewable execution artifact. Это полезная separation source-vs-compiled contract, но docs не доказывают semantic correctness generated workflow.

## Ограничения, recovery, scope

Не описаны product contract, browser acceptance, exact retry taxonomy или autonomous merge. Secrets/permissions need explicit configuration; dynamic agent run in CI can have broad authority if token scopes are broad. GitHub Actions retries/concurrency/branch protection должны быть подключены отдельно.

## WMS-вердикт — адаптировать осторожно

Взять reviewable source + compiled executable config and ordinary CI status as evidence. Не отправлять ночной developer-agent прямо в privileged main/deploy workflow; запускать only isolated branch/worktree, merge после independent gates.

## Evidence

- [official tutorial](https://docs.github.com/en/actions/tutorials/develop-agentic-workflows-in-github-actions)
- [`gh-aw` repository](https://github.com/github/gh-aw)
- [Actions concurrency](https://docs.github.com/en/actions/how-tos/write-workflows/choose-when-workflows-run/control-workflow-concurrency)
- [protected branch rules](https://docs.github.com/en/repositories/configuring-branches-and-merges-in-your-repository/managing-protected-branches/about-protected-branches)
