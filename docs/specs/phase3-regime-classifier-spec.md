# Phase 3 Spec: Regime Classifier

- Version: 1.0
- Date: 2026-05-30
- Related ADR: 0001, 0002, 0003

## 目的
市場を `RANGE | TREND | HIGH_VOL` に分類し、戦略選択と停止判断を安全に制御する。

## 入力（I/O契約）
- Phase 2 特徴量テーブル
- ボラティリティ/トレンド判定パラメータ（閾値設定）

## 出力（I/O契約）
- Regime判定テーブル
  - 主キー: `(symbol, timeframe, timestamp)`
  - カラム:
    - `regime` (`RANGE|TREND|HIGH_VOL`)
    - `confidence` (`0.0-1.0`)
    - `volatility_state` (`normal|elevated|extreme`)
    - `reason_codes`（判定根拠コード配列）
    - `is_trade_allowed`（bool）

## 前提条件
- 判定は時系列順に実施する。
- `HIGH_VOL` は「戦略の一種」ではなく「停止状態」。
- 判定不能（データ不足等）は安全側で `is_trade_allowed=false`。

## 仕様
1. 判定ロジック
- `HIGH_VOL`: ATR極端拡大、急激スプレッド拡大、異常変動検知時。
- `TREND`: ブレイク継続 + モメンタム持続 + 高ADX相当条件。
- `RANGE`: 低ボラ + 平均回帰優位 + フェイクブレイク優勢条件。
- 初期閾値（v1、銘柄別に上書き可）
  - `high_vol.atr_zscore_threshold = 3.0`
  - `high_vol.return_abs_zscore_threshold = 3.0`
  - `trend.adx_threshold = 25`
  - `trend.breakout_persistence_min_bars = 3`
  - `range.bb_width_percentile_max = 40`
  - `range.adx_max = 20`

2. 遷移制御
- Regimeのチャタリング抑制のため最小継続バー数を設定。
- `HIGH_VOL` 遷移時は即時で新規建てを停止。
- `HIGH_VOL` 解除時はクールダウン後に再開可能。
- 初期設定
  - `transition.min_regime_hold_bars = 3`
  - `transition.high_vol_cooldown_bars = 5`

3. 可視化要件
- ローソク足に regime overlay を表示。
- `reason_codes` をGUIから参照可能にする。
- `reason_codes` は以下列挙のみ許可する。
  - `HV_ATR_SPIKE`
  - `HV_RETURN_SPIKE`
  - `HV_SPREAD_WIDENING`
  - `TR_BREAKOUT_PERSIST`
  - `TR_MOMENTUM_PERSIST`
  - `TR_ADX_STRONG`
  - `RG_LOW_VOL`
  - `RG_MEAN_REVERSION_BIAS`
  - `RG_FAKE_BREAKOUT_BIAS`
  - `FALLBACK_INSUFFICIENT_DATA`
  - `FALLBACK_TIMEOUT`
- 監視メトリクス:
  - regime分布
  - HIGH_VOL滞在率
  - 判定信頼度のドリフト

## 失敗モードと対策
- 判定遅延: タイムアウト時は取引停止。
- 閾値過適合: WalkForwardで再現性検証。
- 不正遷移: 状態遷移テーブル違反をエラー化。

## テスト観点
- regime分類ユニットテスト（境界条件）。
- HIGH_VOL時の強制停止テスト。
- 遷移チャタリング抑制テスト。
- reason_codes整合テスト。
