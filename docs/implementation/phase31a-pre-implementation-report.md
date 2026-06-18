# Phase 31A Pre-Implementation Report

## Date: 2026-06-18

## System Performance Baseline

### Current System Status
- Worker cycle time: ~15 seconds (single iteration test)
- Processing: 1 symbol (SOLUSDT), 2 routes (trend + range)
- API calls per cycle: Unknown (needs measurement)
- Current polling interval: 2 seconds
- Timeframe analysis: 15 minutes

### Performance Observations
- Worker execution completes successfully
- Market data fetching works correctly
- Signal generation functional
- No obvious performance bottlenecks in single execution

## Current Market Data Client Analysis

### File: src/auto_trader/worker/market_data.py

**Current Implementation:**
- Simple REST API client for Binance futures
- No caching mechanism
- Individual API calls per symbol/interval
- No rate limiting considerations
- Error handling is basic

**Key Methods:**
- `fetch_klines()`: Fetches OHLCV data from Binance API
- `resample_ohlcv()`: Resamples 1-minute data to target timeframe

**Current Limitations:**
- Every call hits the API regardless of data freshness
- No retry logic for transient failures
- No request batching
- No data freshness validation

## Cache Design Specification

### Cache Storage Location
- **Path**: `data/cache/market_data/`
- **Format**: Parquet files (efficient, columnar, compatible with pandas)
- **File naming**: `{symbol}_{interval}.parquet`

### Cache Key Structure
- Primary key: symbol + interval
- Example: `SOLUSDT_1m.parquet`, `ETHUSDT_15m.parquet`

### Cache Configuration Parameters
```python
@dataclass(frozen=True)
class CacheConfig:
    enabled: bool = False  # Disabled by default for safety
    cache_dir: str = "data/cache/market_data"
    ttl_seconds: int = 60  # 1 minute cache
    max_cache_size_mb: int = 100  # Maximum cache directory size
    cleanup_age_hours: int = 24  # Cleanup files older than this
```

### Cache Validation Strategy
1. **File existence check**: Ensure cache file exists
2. **Timestamp validation**: Check file modification time against TTL
3. **Data integrity**: Verify parquet file can be read
4. **Schema validation**: Ensure data structure matches expected format
5. **Data freshness**: Validate timestamp of oldest data point

### Cache Metadata
Each cached file will include:
- Cache generation timestamp
- Source (API vs cache)
- Data schema version
- Checksum (optional)

### Fallback Mechanism
- Cache read failure → API call
- Cache validation failure → API call
- Staleness detection → API call
- Cache write failure → Continue with API data (log error)

### Cache Cleanup Strategy
1. **Time-based cleanup**: Remove files older than 24 hours
2. **Size-based cleanup**: Remove oldest files if directory exceeds limit
3. **Startup cleanup**: Clean old files on worker startup
4. **Periodic cleanup**: Cleanup every N cycles

## Cache Metrics Plan

### Metrics to Collect
```python
class CacheMetrics:
    cache_hits: int
    cache_misses: int
    cache_errors: int
    cache_hit_rate: float
    api_calls: int
    cache_read_latency_ms: float
    cache_write_latency_ms: float
    api_latency_ms: float
```

### Monitoring Integration
- Add cache metrics to existing runtime metrics
- Update monitor CLI to include cache statistics
- Add cache-specific logging
- Set up alerting for cache performance degradation

## Implementation Approach

### Phase 1: Core Caching Layer
1. Extend BinanceKlineClientConfig with cache parameters
2. Add cache methods to BinanceKlineClient
3. Implement cache validation logic
4. Implement fallback mechanism

### Phase 2: Configuration Integration
1. Add cache configuration to config.py
2. Add cache CLI arguments
3. Update config.local.yaml template
4. Make caching optional/configurable

### Phase 3: Monitoring Integration
1. Add cache metrics collection
2. Update monitor metrics collector
3. Add cache-specific logging
4. Update dashboard if needed

### Phase 4: Testing
1. Unit tests for cache functionality
2. Integration tests with real data
3. Performance benchmarking
4. Fallback mechanism validation

## Safety Considerations

### Risk Mitigation
- **Caching disabled by default**: Gradual rollout
- **Comprehensive validation**: Multiple validation layers
- **Fallback always available**: Never block on cache
- **Extensive monitoring**: Track cache effectiveness
- **Quick disable**: Easy to disable if issues arise

### Error Handling
- All cache operations wrapped in try-catch
- Cache errors logged but don't block execution
- API always available as fallback
- Graceful degradation on cache failure

## Next Steps

1. ✅ Complete pre-implementation analysis
2. ⏭️ Begin cache layer implementation
3. ⏭️ Add configuration integration
4. ⏭️ Implement testing suite
5. ⏭️ Integrate monitoring
6. ⏭️ Staging deployment
7. ⏭️ Production rollout

## Timeline Status

- **Pre-Implementation**: ✅ Complete
- **Design**: ⏭️ In Progress
- **Implementation**: ⏭️ Pending
- **Testing**: ⏭️ Pending
- **Integration**: ⏭️ Pending
