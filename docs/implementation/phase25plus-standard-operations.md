# Phase25+ 標準運用手順（再開版）

- Version: 1.0
- Date: 2026-06-01
- Scope: spec-review / implementation-checklist / go-live checklist 運用

## 目的
- Phase25以降で停止していた文書運用ループを再開する。
- 実装・証跡・判定の責任境界を固定し、引き継ぎ可能な状態を維持する。

## 標準手順
1. Spec更新/追加
- 対象PhaseのSpecを `docs/specs/` に追加または更新する。
- I/O契約、失敗モード、テスト観点を必須で埋める。

2. Spec Review記録
- `docs/implementation/spec-review-phaseXX-YYYY-MM-DD.md` を作成する。
- 結論、固定事項、残留リスク、follow-up を明記する。

3. Implementation Checklist更新
- `docs/implementation/phaseXX-implementation-checklist.md` を更新する。
- Done定義と証跡パスを一致させる。

4. 証跡スクリプト実行
- 週次再評価: `./scripts/weekly_strategy_revalidation.sh`
- longrun / health: `./scripts/longrun_8h_check.sh` または既存証跡の確認

5. Go-Live checklist同期
- `./scripts/update_go_live_checklist.sh`
- 反映前確認は `DRY_RUN=true ./scripts/update_go_live_checklist.sh`

6. 判定確定
- `docs/implementation/trading-go-live-checklist.md` の `Auto Decision Notes` と `判定日` を正本とする。
- Go / Conditional Go / No-Go を本文に確定記録する。

## 運用ルール
- longrun / runtime metrics 判定は従来どおり自動判定を主軸とする。
- weekly revalidation は補助判定とし、`warn` は即No-Goにしない。
- `warn` の場合は symbol gating / cost 仮定の再調整タスクを必ず起票する。

## 引き継ぎチェック
- 最新Spec、Spec Review、Implementation Checklist が同一Phaseで揃っている。
- `update_go_live_checklist.sh` の `Auto Decision Notes` が最新証跡を反映している。
- open item がある場合、Issue または運用TODOへ明示移管されている。
