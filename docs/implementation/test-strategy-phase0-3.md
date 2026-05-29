# テスト戦略（Phase 0-3）

## 目的
仕様抜け・リーク・安全性欠陥を早期に検出し、実運用前に停止できる状態を作る。

## Unit Test 最低ケース
1. Phase 0
- 設定優先順位（env > config > default）
- `prod` 起動ガード
- ログ必須キー検証

2. Phase 1
- 欠損検知
- 重複検知
- UTC正規化
- リジューム整合

3. Phase 2
- 指標算出（RSI/ATR/BB等）境界値
- warmup除外
- 未来参照検知

4. Phase 3
- regime境界判定
- HIGH_VOL強制停止
- reason_codes整合

## Integration Test 最低ケース
1. Data -> Feature -> Regime のE2E整合
2. 判定不能データ入力時に安全停止すること
3. 監視メトリクス出力が欠損しないこと

## Simulation Test 最低ケース
1. 急変動（flash crash）相当入力で `HIGH_VOL` に遷移
2. APIタイムアウト時の再試行と停止挙動
3. 欠損データ連続時の新規建て停止

## 受け入れ基準
- `base_policy.md` の禁止事項がテスト項目に反映されている。
- no shuffle / no leakage を自動検証できる。
- HIGH_VOL時の取引停止が自動テストで担保される。
