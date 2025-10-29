# Development Guidelines

## API Implementation Rules

### ⚠️ CRITICAL: Never Guess API Responses

**ALWAYS verify against official DataForSEO documentation before implementing or modifying API interactions.**

### Rule 1: Documentation First

Before implementing ANY DataForSEO API functionality:

1. **Find the official documentation page**
2. **Read the complete endpoint documentation**
3. **Verify the exact response structure**
4. **Check status codes**
5. **Only then write code**

### Rule 2: Required Documentation Links

For each API endpoint used, document the official docs link:

```python
def some_api_function():
    """
    Description of function.
    
    DataForSEO Documentation:
    https://docs.dataforseo.com/v3/serp-google-organic-task_post/
    
    Response structure verified: [Date]
    """
```

### Rule 3: Verification Checklist

Before committing any API-related code, verify:

- [ ] Official documentation URL is referenced
- [ ] Response structure matches docs exactly
- [ ] Status codes are correct (20000, 20100, etc.)
- [ ] Error handling covers documented error codes
- [ ] Field names match documentation exactly
- [ ] Data types match documentation

### Rule 4: Test Against Docs

When debugging API issues:

1. **Don't guess** - Check the docs first
2. **Log the actual response** from the API
3. **Compare** logged response to documentation
4. **Fix** discrepancies between code and docs
5. **Document** what was wrong

## DataForSEO Documentation Index

### Core SERP API Endpoints

#### Task POST (Standard Mode)
- **URL**: https://docs.dataforseo.com/v3/serp-google-organic-task_post/
- **Response**: `tasks[].id` (string, directly in task object)
- **Success Status**: `20100` = task created
- **Use for**: Posting tasks for async processing

#### Task GET Advanced (Standard Mode)
- **URL**: https://docs.dataforseo.com/v3/serp-google-organic-task-get-advanced/
- **Response**: `tasks[].result[].keyword`, `tasks[].result[].items[]`
- **Success Status**: `20000` = task completed
- **Use for**: Retrieving results from posted tasks

#### Tasks Ready
- **URL**: https://docs.dataforseo.com/v3/serp-google-organic-tasks-ready/
- **Response**: `tasks[].result[].id` (array of ready task IDs)
- **Use for**: Checking which tasks are ready to retrieve

#### Live Advanced (Live Mode)
- **URL**: https://docs.dataforseo.com/v3/serp-google-organic-live-advanced/
- **Response**: Same as Task GET Advanced
- **Success Status**: `20000` = immediate results
- **Use for**: Getting immediate results

### Supporting Endpoints

#### Locations
- **URL**: https://docs.dataforseo.com/v3/serp/google/locations/
- **Response**: `tasks[].result[]` (array of location objects)
- **Fields**: `location_code`, `location_name`, `country_iso_code`, `location_type`

#### Languages
- **URL**: https://docs.dataforseo.com/v3/serp/google/languages/
- **Response**: `tasks[].result[]` (array of language objects)
- **Fields**: `language_code`, `language_name`

### Status Codes Reference

**URL**: https://docs.dataforseo.com/v3/appendix-errors/

Common status codes:
- `20000` - Successful (task completed/retrieved)
- `20100` - Successful (task created)
- `40101` - Authentication failed
- `40102` - Incorrect or insufficient parameters
- `40103` - Requested functionality is not available
- `50000` - Internal server error (retry)

## Example: Proper Implementation Process

### ❌ WRONG Approach:
```python
# Just guessing the structure
def post_tasks(payload):
    response = api.post(payload)
    task_id = response['result']['id']  # WRONG! Guessing structure
    return task_id
```

### ✅ CORRECT Approach:

```python
def post_tasks(payload):
    """
    Post tasks to DataForSEO SERP API.
    
    Official Documentation:
    https://docs.dataforseo.com/v3/serp-google-organic-task_post/
    
    Verified Response Structure (2024-10-29):
    {
      "tasks": [{
        "id": "string",           // Task ID is HERE
        "status_code": 20100,     // 20100 = successfully created
        "result": null            // Result is NULL for task_post
      }]
    }
    """
    response = api.post(payload)
    
    # Extract ID per documentation
    task = response.get("tasks", [{}])[0]
    if task.get("status_code") == 20100:
        task_id = task.get("id")  # Directly from task object
        return task_id
    else:
        raise APIError(f"Task creation failed: {task.get('status_message')}")
```

## Code Review Checklist

Before approving any PR with API changes:

- [ ] Documentation URL is cited
- [ ] Response structure matches docs
- [ ] Status codes are correct
- [ ] Error handling is complete
- [ ] No assumptions or guesses
- [ ] Test output logged and compared to docs

## Future API Additions

When adding new DataForSEO APIs (Keywords Data, Backlinks, OnPage):

1. **Start with documentation**: Read the full API docs
2. **Create client class**: Inherit from `DataForSEOClient`
3. **Document structure**: Add response structure comments
4. **Add to this file**: Update the documentation index
5. **Test thoroughly**: Compare real responses to docs

## Resources

- **Main DataForSEO Docs**: https://docs.dataforseo.com/
- **SERP API Overview**: https://docs.dataforseo.com/v3/serp/overview/
- **Error Codes**: https://docs.dataforseo.com/v3/appendix-errors/
- **Status Codes**: https://docs.dataforseo.com/v3/appendix-errors/
- **Rate Limits**: https://dataforseo.com/help-center/rate-limits-and-request-limits

## Remember

> "When in doubt, check the docs. When sure, check the docs anyway."

**Never assume. Always verify.**

