# Phase 31A Safety & Rollback Procedures

## Date: 2026-06-18

## Safety Measures

### 1. Default Safety: Caching Disabled by Default
- **Risk Mitigation**: Caching is disabled by default in all configurations
- **Implementation**: `cache_enabled: bool = False` in all config defaults
- **Activation**: Requires explicit CLI flag or configuration change
- **Benefit**: No accidental cache usage, deliberate enablement only

### 2. Comprehensive Fallback Mechanism
- **Fallback Strategy**: API always available as fallback
- **Failure Scenarios**:
  - Cache read failure → API call
  - Cache validation failure → API call
  - Staleness detection → API call
  - Cache write failure → Continue with API data (log error)
- **Guarantee**: Cache never blocks worker execution

### 3. Conservative TTL Setting
- **Cache Duration**: 60 seconds (1 minute)
- **Rationale**: Aligned with 1-minute market data update intervals
- **Risk Limitation**: Limits staleness to 1 minute maximum
- **Market Adaptation**: Allows rapid response to market changes

### 4. Cache Validation Layers
1. **File Existence Check**: Ensures cache file exists
2. **Timestamp Validation**: Checks file age against TTL
3. **Data Integrity**: Verifies Parquet file can be read
4. **Schema Validation**: Ensures data structure matches expected format

### 5. Error Handling
- **Try-Catch Wrapping**: All cache operations wrapped in error handling
- **Non-Critical Failures**: Cache write failures don't block execution
- **Error Logging**: All cache errors logged for monitoring
- **Graceful Degradation**: System continues functioning on cache errors

### 6. Simple Implementation
- **No External Dependencies**: Uses only filesystem and existing libraries
- **Minimal Code Changes**: Limited interface modifications
- **Easy to Understand**: Clear, straightforward implementation
- **Easy to Disable**: Simple to turn off if issues arise

## Rollback Procedures

### Immediate Rollback (Emergency)

**Scenario**: Cache causing critical issues, immediate rollback needed

**Steps**:
1. **Disable Caching via CLI**:
   ```bash
   # Remove --cache-enabled flag from worker command
   python -m auto_trader.worker [other args]  # Without --cache-enabled
   ```

2. **Disable Caching via Config**:
   ```yaml
   # config/config.local.yaml
   worker:
     cache_enabled: false  # Set to false
   ```

3. **Clear Cache Directory**:
   ```bash
   rm -rf data/cache/market_data/
   ```

4. **Restart Worker**:
   ```bash
   # Stop current worker
   pkill -f "auto_trader.worker"

   # Start worker without cache
   python -m auto_trader.worker [args without --cache-enabled]
   ```

**Time to Rollback**: < 2 minutes
**Risk**: Very Low (system continues with API calls)

### Configuration Rollback

**Scenario**: Need to revert configuration changes only

**Steps**:
1. **Revert config.local.yaml**:
   ```yaml
   worker:
     # Remove cache section entirely or set to false
     # cache_enabled: false
     # cache_dir: data/cache/market_data
     # cache_ttl_seconds: 60
   ```

2. **Restart Worker**:
   ```bash
   pkill -f "auto_trader.worker"
   python -m auto_trader.worker [existing args]
   ```

**Time to Rollback**: < 1 minute
**Risk**: None (config changes only)

### Code Rollback

**Scenario**: Need to revert code changes

**Steps**:
1. **Git Revert**:
   ```bash
   git checkout HEAD~1 -- src/auto_trader/worker/market_data.py
   git checkout HEAD~1 -- src/auto_trader/worker/runner.py
   git checkout HEAD~1 -- src/auto_trader/worker/cli.py
   ```

2. **Restart Worker**:
   ```bash
   pkill -f "auto_trader.worker"
   python -m auto_trader.worker [existing args]
   ```

**Time to Rollback**: < 5 minutes
**Risk**: Low (git revert is safe)

## Monitoring for Safety Issues

### Cache Performance Metrics to Monitor

**Critical Metrics**:
1. **Cache Hit Rate**: Should be > 50% (target > 90%)
2. **Cache Error Rate**: Should be < 1%
3. **API Call Rate**: Should decrease significantly with caching
4. **Cache Read Latency**: Should be < API latency

**Warning Indicators**:
- Cache hit rate < 50%: Cache may not be effective
- Cache error rate > 5%: Cache implementation issues
- Stale data detected: TTL may be too long
- Performance degradation: Cache may be overhead

### Automated Alerting

**Alert Conditions**:
```yaml
cache_hit_rate_below_50:
  condition: cache_hit_rate < 0.5
  severity: warning
  action: Review cache configuration

cache_error_rate_high:
  condition: cache_error_rate > 0.05
  severity: critical
  action: Disable caching, investigate errors

stale_data_detected:
  condition: staleness_incident > 0
  severity: critical
  action: Disable caching immediately, investigate TTL
```

### Manual Monitoring

**Daily Checks**:
1. Review cache metrics in worker output
2. Check cache directory size
3. Monitor API call reduction
4. Verify no stale data incidents

**Weekly Checks**:
1. Analyze cache hit rate trends
2. Review cache error logs
3. Validate performance improvements
4. Check for memory leaks

## Testing Rollback Procedures

### Test 1: CLI Disable Rollback
**Purpose**: Verify CLI disable works correctly

**Steps**:
```bash
# Start with cache enabled
python -m auto_trader.worker --cache-enabled --max-iterations 1

# Stop and restart without cache
python -m auto_trader.worker --max-iterations 1

# Verify: No cache files accessed, API calls made normally
```

**Expected**: System works without cache, no errors

### Test 2: Config Disable Rollback
**Purpose**: Verify config disable works correctly

**Steps**:
```yaml
# Enable cache in config
worker:
  cache_enabled: true

# Run worker
python -m auto_trader.worker

# Disable cache in config
worker:
  cache_enabled: false

# Restart worker
python -m auto_trader.worker
```

**Expected**: System respects config change, works without cache

### Test 3: Cache Clear Rollback
**Purpose**: Verify cache clearing works correctly

**Steps**:
```bash
# Run with cache enabled
python -m auto_trader.worker --cache-enabled --max-iterations 1

# Clear cache
rm -rf data/cache/market_data/

# Run again
python -m auto_trader.worker --cache-enabled --max-iterations 1

# Verify: Cache recreated, system works normally
```

**Expected**: Cache recreated, no errors, normal operation

### Test 4: Error Scenario Rollback
**Purpose**: Verify system handles cache errors gracefully

**Steps**:
```bash
# Corrupt cache file
echo "corrupted" > data/cache/market_data/SOLUSDT_1m.parquet

# Run worker
python -m auto_trader.worker --cache-enabled --max-iterations 1

# Verify: Falls back to API, no crashes, error logged
```

**Expected**: Falls back to API, continues execution, error logged

## Decision Criteria for Rollback

### Automatic Rollback Triggers
1. **Cache Error Rate > 10%**: Automatic disable recommended
2. **Stale Data Detected**: Immediate disable required
3. **Performance Degradation > 20%**: Disable and investigate
4. **Memory Issues**: Disable and investigate

### Manual Rollback Considerations
1. **Cache Hit Rate < 30%**: Consider disable (ineffective)
2. **Complex Debugging Needed**: Temporary disable for investigation
3. **Production Issues**: Disable immediately, investigate later

### Rollback Decision Flow
```
Issue Detected
    ↓
Is Cache Related?
    ↓ Yes
Can Fix Quickly?
    ↓ No
Is System Stable?
    ↓ Yes
Monitor with Cache Disabled
    ↓
Issue Resolved?
    ↓ Yes
Investigate Root Cause
    ↓
Fix Identified
    ↓
Test Fix
    ↓
Deploy Fix
    ↓
Re-enable Caching with Monitoring
```

## Emergency Contacts and Procedures

### Emergency Scenarios

**Scenario 1: Cache Causing Trading Issues**
1. Immediately disable caching (CLI or config)
2. Clear cache directory
3. Restart worker
4. Monitor trading operations
5. Document incident

**Scenario 2: Cache Corruption**
1. Clear cache directory
2. Restart worker without cache
3. Investigate corruption cause
4. Fix root cause
5. Re-enable with monitoring

**Scenario 3: Performance Degradation**
1. Disable caching
2. Measure baseline performance
3. Analyze cache metrics
4. Investigate performance impact
5. Optimize or disable permanently

## Post-Rollback Validation

### Validation Checklist
- [ ] Worker starts successfully without cache
- [ ] Trading operations normal
- [ ] API calls functioning
- [ ] No error logs related to cache
- [ ] Performance baseline restored
- [ ] Monitoring shows normal metrics
- [ ] Cache directory cleared (if applicable)

### Monitoring After Rollback
- Monitor worker for 1 hour post-rollback
- Check error logs for cache-related errors
- Verify trading performance
- Confirm API call rates normal
- Validate system stability

## Documentation Updates

### After Rollback
1. Document rollback reason
2. Record timeline of events
3. Note any system impact
4. Update procedures if needed
5. Share lessons learned

## Conclusion

The safety and rollback procedures for Phase 31A provide multiple layers of protection:

1. **Default Safety**: Caching disabled by default
2. **Immediate Rollback**: Quick disable capability
3. **Comprehensive Fallback**: API always available
4. **Monitoring**: Extensive metric collection
5. **Testing**: Validated rollback procedures
6. **Documentation**: Clear procedures and criteria

The system can be safely rolled back in < 2 minutes if issues arise, with minimal risk to trading operations. The conservative implementation approach ensures that caching is an optional enhancement rather than a critical dependency.
