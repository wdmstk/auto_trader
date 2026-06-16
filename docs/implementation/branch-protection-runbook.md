# Branch Protection Runbook（Phase 22）

## 目的
`main` を required checks ベースで保護し、品質ゲートを強制する。

## 必須チェック
- `coverage`
- `full`
- `smoke`

## GitHub設定（Repository Settings）
1. `Settings > Branches > Add rule`
2. Branch name pattern: `main`
3. `Require a pull request before merging` を有効化
4. `Require status checks to pass before merging` を有効化
5. Required checks に `coverage`, `full`, `smoke` を登録
6. 可能なら `Do not allow bypassing` を有効化

## ローカル検証
```bash
.venv/bin/python scripts/validate_required_checks.py
```

## 変更時ルール
- `.github/workflows/ci.yml` のジョブ名変更時は、required checks定義とRunbookを同時更新する。
