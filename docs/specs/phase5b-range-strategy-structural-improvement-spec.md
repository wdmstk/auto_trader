# Phase 5b Spec: RANGE Strategy Structural Improvement

- Version: 1.0
- Date: 2026-06-23
- Parent: phase5-range-strategy-spec.md

## 背景

Phase 5 初期実装ではパラメータ探索 (72 パターン) の結果すべてで PF < 1.0。
根本原因:
1. エントリースコアが機能していない (全条件を個別に AND 要求するため score 閾値が無意味)
2. サポート/レジスタンス構造の認識がない (BB 中心回帰のみ)
3. 出来高確認なし (反発の根拠が薄い)

## 目的

エントリー精度を構造的に改善し PF >= 1.2 到達を目指す。

## 変更概要

### 1. 新特徴量の追加 (features/engine.py)

| Feature | 定義 | 用途 |
|---------|------|------|
| `bb_position` | `(close - bb_lower) / (bb_upper - bb_lower)` | BB 内での価格位置 (0=下限, 1=上限) |
| `price_vs_recent_low` | `(close - rolling_low_N) / atr` | 直近サポートからの乖離度 |
| `volume_spike` | `volume_ratio > volume_spike_threshold` (bool→int) | 反発時の出来高確認 |

### 2. エントリーロジック変更 (range_strategy.py)

**旧**: `entry = score_ok AND rsi_ok AND wick_ok AND mr_ok AND rev_ok`
(score は冗長; 全条件 AND なので min_entry_score が機能しない)

**新**: 重み付きスコアリング方式
```
score = (
    w_rsi * rsi_ok +
    w_wick * wick_ok +
    w_mr * mr_ok +
    w_bb_pos * bb_position_ok +
    w_vol * volume_ok
) / total_weight
entry = regime_gate AND score >= min_entry_score
```

- `reversal_candle_flag` は重み付きスコアに含めず、ボーナスとして加算
- 個別条件の AND 強制を廃止し、min_entry_score が実質的なフィルタとして機能
- `bb_position_ok`: `bb_position < bb_position_max` (BB 下部のみエントリー)

### 3. Config 拡張

```python
@dataclass(frozen=True)
class RangeStrategyConfig:
    # 既存
    rsi_min: float = 35.0
    rsi_max: float = 55.0
    wick_ratio_min: float = 0.3
    mean_reversion_distance_max: float = -0.3
    exit_mean_reversion_neutral_abs: float = 0.15
    min_entry_score: float = 0.6  # 実効閾値に変更
    max_hold_bars: int = 16
    # 新規
    bb_position_max: float = 0.35  # BB下部35%以下でのみエントリー
    volume_spike_threshold: float = 1.3  # volume_ratio 閾値
    price_vs_recent_low_max: float = 1.5  # ATR 1.5 倍以内
    recent_low_window: int = 20  # サポート判定用ルックバック
    # 重み
    w_rsi: float = 1.0
    w_wick: float = 1.0
    w_mr: float = 1.5  # BB乖離は重要度高
    w_bb_pos: float = 2.0  # BB下部位置は最重要
    w_vol: float = 1.0
    w_reversal_bonus: float = 0.5  # reversal candle はボーナス
```

### 4. エグジット改善

既存ロジック維持 + ATR ベーストレーリングストップを追加:
- `exit_atr_trail_multiplier: float = 2.0`: エントリー後の最安値 + ATR*multiplier を超えたら利確

## 前提条件

- 既存の regime gate (RANGE 以外停止) は変更しない
- risk_blocked 制御は変更しない
- ML フィルタは既存パイプラインで別途適用される (本変更のスコープ外)

## テスト観点

- 旧テストの regime/risk_blocked/HIGH_VOL ロジックは維持
- 新テスト: bb_position がフィルタとして機能すること
- 新テスト: volume_spike が score に寄与すること
- 新テスト: min_entry_score が実効的にフィルタすること (score=0.5 と score=0.8 で結果が異なる)
- 新テスト: ATR トレーリングストップが機能すること

## 失敗モードと対策

- エントリー過少: min_entry_score を下げる or 重みを調整
- 特徴量 NaN: rolling 期間不足時は feature = neutral value にフォールバック
- 過学習リスク: walkforward で OOS 評価を必須とする
