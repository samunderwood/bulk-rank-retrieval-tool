# DataForSEO API Implementation Findings

## 🚨 Critical Issue Discovered & Fixed

### The Problem
The `target` parameter in DataForSEO SERP API **only works in Live mode**, NOT in Standard mode (task_post/task_get).

### What We Were Doing Wrong
```python
# WRONG: Using 'target' in Standard mode
payload = [{
    "keyword": kw,
    "language_code": language_code,
    "location_code": int(location_code),
    "target": domain,  # ❌ This doesn't work in Standard mode!
    "device": device,
    "depth": int(depth)
}]
```

### The Correct Approach (Per DataForSEO Docs)

#### For Live Mode ✅
```python
# CORRECT: 'target' works in Live mode
payload = [{
    "keyword": kw,
    "target": domain,  # ✅ This works!
    "location_code": location_code,
    "language_code": language_code,
    "device": device,
    "depth": depth
}]
```

#### For Standard Mode ✅
```python
# CORRECT: No 'target' parameter - get ALL results, filter client-side
payload = [{
    "keyword": kw,
    "location_code": location_code,
    "language_code": language_code,
    "device": device,
    "depth": depth
}]

# Then filter results by parsing URLs:
from urllib.parse import urlparse

for item in results:
    url = item.get("url")
    parsed = urlparse(url)
    domain = parsed.netloc.lower().replace('www.', '')
    
    if domain == target_domain or domain.endswith('.' + target_domain):
        # Match found!
        pass
```

## 📚 References

1. **Official Documentation**:
   - [Track Rankings with SERP API](https://dataforseo.com/help-center/track-rankings-with-serp-api)
   - States: "Use `target` parameter available when setting Live Google Organic SERP API tasks"
   
2. **Official Example Script**:
   - See `example-script.py` (from DataForSEO team)
   - Shows Standard mode WITHOUT `target` parameter
   - Demonstrates client-side URL parsing and domain filtering

## ✅ What We Fixed

1. **Removed `target` from Standard mode** payloads
2. **Added domain filtering logic** in `parse_serp_record()` function
3. **URL parsing** to match domains correctly (handles www, subdomains, protocols)
4. **Kept `target` in Live mode** (where it works properly)

## 🎯 Result

- **Live Mode**: Uses `target` parameter → Fast, efficient, works perfectly ✅
- **Standard Mode**: Gets all results → Filters client-side → Now works correctly ✅

## 💡 Key Takeaway

**Always check official documentation AND example scripts** from API providers. The docs mentioned this limitation, but the example script made it crystal clear!

