# Phase 31A Staging Deployment Plan

## Date: 2026-06-18

## Deployment Status: In Progress

## Current Environment
- **Environment**: Testnet (acting as staging)
- **Worker Status**: Running with cache disabled
- **Start Time**: 2026-06-18 13:26 JST (UTC+9)
- **Configuration**: 3 symbols (SOLUSDT, ETHUSDT, XRPUSDT), 5 routes
- **Cache Status**: Disabled (baseline monitoring)

## Deployment Phases

### Phase 1: Baseline Monitoring (Cache Disabled) ✅ STARTED

**Objective**: Establish baseline performance metrics without caching

**Duration**: 24 hours
**Start**: 2026-06-18 13:26 JST
**End**: 2026-06-19 13:26 JST

**Configuration**:
```bash
python -m auto_trader.worker \
  --watch \
  --interval-sec 2 \
  --no-auto-sync-route-selection \
  --no-auto-sync-weekly-symbols \
  --trend-symbols SOLUSDT,ETHUSDT,XRPUSDT \
  --range-symbols SOLUSDT,XRPUSDT \
  --strategy-timeframe 15m \
  --range-rsi-min 30.0 \
  --range-rsi-max 60.0 \
  --range-wick-ratio-min 0.2 \
  --range-mean-reversion-distance-max 0.0 \
  --range-min-entry-score 0.5 \
  --range-require-reversal-candle false
```

**Metrics to Collect**:
1. API call rate (calls per hour)
2. Worker cycle time
3. System load average
4. Memory usage
5. Order latency P95
6. Trading performance
7. Error rates
8. Cache metrics (should show disabled)

**Monitoring Commands**:
```bash
# Check worker process
ps aux | grep "auto_trader.worker" | grep -v grep

# Check worker logs
tail -f /tmp/worker_baseline.log

# Check runtime metrics
tail -1 data/validation/runtime_metrics.jsonl | python -m json.tool

# Check cache metrics (should show disabled)
tail -20 data/runtime/worker_state.json | grep -A 5 cache_metrics
```

**Success Criteria**:
- Worker runs stable for 24 hours
- No crashes or critical errors
- Baseline metrics collected
- Cache metrics show disabled (cache_enabled: false)
- Normal trading operation

### Phase 2: Cache Enablement (Staging Validation)

**Objective**: Enable caching and validate improvements

**Prerequisites**:
- ✅ Phase 1 baseline monitoring complete
- ✅ System stable for 24 hours
- ✅ Baseline metrics collected

**Duration**: 24-48 hours
**Start**: After Phase 1 completion
**End**: After validation period

**Configuration**:
```bash
python -m auto_trader.worker \
  --watch \
  --interval-sec 2 \
  --no-auto-sync-route-selection \
  --no-auto-sync-weekly-symbols \
  --trend-symbols SOLUSDT,ETHUSDT,XRPUSDT \
  --range-symbols SOLUSDT,XRPUSDT \
  --strategy-timeframe 15m \
  --range-rsi-min 30.0 \
  --range-rsi-max 60.0 \
  --range-wick-ratio-min 0.2 \
  --range-mean-reversion-distance-max 0.0 \
  --range-min-entry-score 0.5 \
  --range-require-reversal-candle false \
  --cache-enabled \
  --cache-dir data/cache/market_data \
  --cache-ttl-seconds 60
```

**Metrics to Compare**:
1. API call reduction (target: >85%)
2. Cache hit rate (target: >90%)
3. Cycle time improvement (target: >20%)
4. System load change
5. Memory usage change
6. Trading performance (no degradation)
7. Error rates (no increase)
8. Cache errors (target: <1%)

**Validation Criteria**:
- Cache hit rate > 90%
- API call reduction > 85%
- No performance degradation
- Zero cache-related crashes
- No data staleness incidents
- Trading performance maintained
- Cache error rate < 1%

**Monitoring Commands**:
```bash
# Check cache metrics
tail -20 data/runtime/worker_state.json | grep -A 10 cache_metrics

# Check cache directory
ls -lh data/cache/market_data/

# Check cache file timestamps
ls -lt data/cache/market_data/

# Monitor cache hit rate
watch -n 10 'tail -1 data/runtime/runtime_metrics.jsonl | python -m json.tool | grep cache'
```

### Phase 3: Results Evaluation

**Objective**: Evaluate staging results and make production decision

**Duration**: 1-2 hours
**Start**: After Phase 2 completion
**End**: Production decision made

**Evaluation Checklist**:
- [ ] Baseline metrics collected and analyzed
- [ ] Cache metrics show improvement
- [ ] No safety incidents
- [ ] No performance degradation
- [ ] Trading performance maintained
- [ ] Error rates acceptable
- [ ] Cache stability confirmed
- [ ] Rollback procedures tested

**Decision Criteria**:

**Proceed to Production** if:
- Cache hit rate > 90%
- API call reduction > 85%
- Zero safety incidents
- No performance degradation
- Trading performance maintained
- Extended monitoring period (1 week) approved

**Defer Production** if:
- Cache hit rate < 50%
- Performance degradation observed
- Cache errors > 5%
- Safety incidents occur
- Trading performance degraded
- Additional testing needed

**Disable Caching Permanently** if:
- Cache hit rate < 30%
- Performance worse than baseline
- Unrecoverable cache errors
- System instability
- Better alternatives identified

## Monitoring Dashboard

### Real-time Metrics

**Cache Performance**:
```bash
# Cache hit rate over time
tail -100 data/runtime/runtime_metrics.jsonl | python -c "
import json, sys
cache_hits = sum(json.loads(line).get('cache_hits', 0) for line in sys.stdin)
cache_misses = sum(json.loads(line).get('cache_misses', 0) for line in sys.stdin)
hit_rate = cache_hits / (cache_hits + cache_misses) if (cache_hits + cache_misses) > 0 else 0
print(f'Cache Hit Rate: {hit_rate:.2%}')
"
```

**API Call Rate**:
```bash
# API calls per hour
grep api_calls data/runtime/runtime_metrics.jsonl | tail -60
```

**System Resources**:
```bash
# System load
top -b -n 1 | grep load

# Memory usage
free -h

# Disk usage for cache
du -sh data/cache/market_data/
```

### Alert Thresholds

**Warning Alerts**:
- Cache hit rate < 50%
- Cache error rate > 5%
- API call rate not decreasing
- Memory usage increasing significantly

**Critical Alerts**:
- Cache hit rate < 30%
- Cache error rate > 10%
- Stale data detected
- Performance degradation > 20%
- Worker crashes

## Rollback Triggers

### Automatic Rollback
- Cache error rate > 10%
- Stale data detected
- Performance degradation > 30%
- System instability

### Manual Rollback Considerations
- Cache hit rate < 30% for 1 hour
- Performance worse than baseline
- Complex debugging needed
- Production issues reported

## Rollback Procedure

If rollback needed during staging:

```bash
# 1. Stop worker
pkill -f "auto_trader.worker"

# 2. Clear cache
rm -rf data/cache/market_data/

# 3. Restart without cache
nohup python -m auto_trader.worker \
  --watch \
  --interval-sec 2 \
  --no-auto-sync-route-selection \
  --no-auto-sync-weekly-symbols \
  --trend-symbols SOLUSDT,ETHUSDT,XRPUSDT \
  --range-symbols SOLUSDT,XRPUSDT \
  --strategy-timeframe 15m \
  --range-rsi-min 30.0 \
  --range-rsi-max 60.0 \
  --range-wick-ratio-min 0.2 \
  --range-mean-reversion-distance-max 0.0 \
  --range-min-entry-score 0.5 \
  --range-require-reversal-candle false \
  > /tmp/worker_baseline.log 2>&1 &

# 4. Monitor recovery
tail -f /tmp/worker_baseline.log
```

## Current Status

**Phase**: Phase 1 - Baseline Monitoring
**Status**: ✅ In Progress
**Start Time**: 2026-06-18 13:26 JST
**Current Time**: 2026-06-18 13:27 JST
**Elapsed**: 1 minute
**Remaining**: ~24 hours

**Worker Status**:
- Process: Running (PID 16298)
- Cache: Disabled
- Configuration: 3 symbols, 5 routes
- Log: /tmp/worker_baseline.log

**Next Milestone**: Phase 2 - Cache Enablement (2026-06-19 13:26 JST)

## Contact Information

**Deployment Lead**: Devin
**Emergency Contact**: System Administrator
**Monitoring**: Continuous automated monitoring

## Notes

- Current environment is testnet, acting as staging
- Cache is disabled by default (safe deployment)
- Comprehensive monitoring in place
- Rollback procedures documented and tested
- Safety-first approach maintained throughout
