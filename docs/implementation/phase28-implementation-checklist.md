# Phase 28 実装チェックリスト（Volatility-Weighted Exposure）

## 実装前に固定する事項
- [x] 制御優先順位（block優先/size_scale優先）を固定
  - 初期値: `block優先`（hard threshold超過時）、それ以外は `size_scale` 適用
- [x] `size_scale` 下限値と最小発注サイズの関係を固定
  - 初期値: `size_scale` 下限 `0.25`、最小発注サイズ未満は新規建て拒否
- [x] rolling window 長と更新頻度を固定
  - 初期値: `window=96 bars`（15m運用で約24h）、更新頻度は毎バー
- [x] 欠損時フォールバック（安全側縮小/建て禁止）を固定
  - 初期値: 欠損比率 `<0.20` は `size_scale=0.5`、`>=0.20` は新規建て禁止

## 実装項目
- [ ] risk入力へ volatility 指標導線を追加
- [ ] risk contribution 算出ロジックを追加
- [ ] vol weighted exposure 判定を追加
- [ ] block reason `RISK_VOL_WEIGHTED_EXPOSURE` を追加
- [ ] size_scale 導線を追加
- [ ] GUI/レポート表示を追加
- [ ] テストを追加

## Done定義
- [ ] 急騰銘柄でリスク寄与が増加することを再現できる
- [ ] 閾値超過時に block または縮小が機能する
- [ ] 既存相関ゲートと矛盾しない
- [ ] 指標計算の再現性（window/頻度）が担保される
- [ ] spec-review を作成済み
