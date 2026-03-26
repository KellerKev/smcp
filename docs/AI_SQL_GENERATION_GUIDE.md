# AI-Driven SQL Generation Guide

## Overview

This guide documents the AI-driven SQL generation capabilities of the SMCP-DuckDB integration, including best practices for working with different language models and handling their limitations.

## Architecture

```
┌──────────────────────────────────────────────────────────┐
│                   Business Question                       │
│              "What are our top customers?"                │
└────────────────────────┬─────────────────────────────────┘
                         ↓
┌──────────────────────────────────────────────────────────┐
│                   Schema Discovery                        │
│         Automatic extraction of table structure           │
└────────────────────────┬─────────────────────────────────┘
                         ↓
┌──────────────────────────────────────────────────────────┐
│                  AI Model (Mistral 7B)                    │
│            Natural Language → SQL Translation             │
└────────────────────────┬─────────────────────────────────┘
                         ↓
┌──────────────────────────────────────────────────────────┐
│                 SMCP DuckDB Connector                     │
│                   Query Execution                         │
└────────────────────────┬─────────────────────────────────┘
                         ↓
┌──────────────────────────────────────────────────────────┐
│                   AI Analysis                             │
│              Business Intelligence Report                 │
└──────────────────────────────────────────────────────────┘
```

## Model Capabilities & Requirements

### Small Models (7B Parameters)
**Examples**: Mistral 7B, Llama 2 7B, Vicuna 7B

#### Characteristics:
- Limited context understanding
- Prone to syntax errors in complex queries
- Inconsistent alias usage
- May attempt invalid operations (e.g., AVG on text columns)

#### Requirements:
- **Explicit SQL templates** for complex queries
- **Detailed schema information** with data types
- **Clear examples** of correct vs incorrect patterns
- **Domain-specific guidance** for multi-table JOINs

#### Implementation:
```python
# Small models need explicit templates
sql_template = """
SELECT 
    table1.column1,
    COUNT(*) as count,
    AVG(table2.numeric_column) as average
FROM table1
JOIN table2 ON table1.id = table2.foreign_id
GROUP BY table1.column1
ORDER BY count DESC
LIMIT 10;
"""

prompt = f"""
Use this EXACT SQL structure for the question: {question}
{sql_template}
Return ONLY the SQL query.
"""
```

### Medium Models (13B-70B Parameters)
**Examples**: Llama 2 13B/70B, Vicuna 13B, WizardLM 70B

#### Characteristics:
- Better SQL syntax understanding
- Can handle moderate complexity without templates
- Occasional alias consistency issues
- Generally reliable for standard queries

#### Requirements:
- **Schema with examples** but not full templates
- **Clear JOIN requirements**
- **Data type specifications**

#### Implementation:
```python
# Medium models need schema and guidelines
prompt = f"""
Generate SQL for: {question}

Schema:
{schema_with_types}

Rules:
- Use consistent aliases throughout
- Join all referenced tables
- Return only the SQL query

Example pattern:
SELECT columns FROM table1 t1 
JOIN table2 t2 ON t1.id = t2.foreign_id
"""
```

### Large Models (>70B Parameters)
**Examples**: GPT-4, Claude 3.5, Llama 3 405B

#### Characteristics:
- Excellent SQL generation from natural language
- Understands complex business logic
- Handles multi-table JOINs naturally
- Optimizes queries automatically

#### Requirements:
- **Basic schema** information only
- **Natural language** question
- No templates needed

#### Implementation:
```python
# Large models work with minimal guidance
prompt = f"""
Generate a SQL query for this question: {question}

Available tables:
{simple_schema}

Return only the SQL query.
"""
```

## Template Strategy by Domain Complexity

### Simple Domains (1-2 tables)
```python
def generate_simple_sql(question, schema, model_size):
    if model_size < "13B":
        return use_template()
    else:
        return direct_generation(question, schema)
```

### Complex Domains (3+ tables with relationships)
```python
def generate_complex_sql(question, schema, model_size):
    if model_size < "13B":
        return use_exact_template()  # Full SQL template
    elif model_size < "70B":
        return use_pattern_template()  # SQL pattern with placeholders
    else:
        return direct_generation(question, schema)
```

## Common Issues and Solutions

### Issue 1: Alias Inconsistency
**Problem**: Model uses both full table names and aliases
```sql
-- Wrong
SELECT ss.plan, saas_users.user_id 
FROM saas_subscriptions ss ...
```

**Solution**: Enforce consistent alias usage in template
```sql
-- Correct
SELECT ss.plan, su.user_id 
FROM saas_subscriptions ss
JOIN saas_users su ...
```

### Issue 2: Missing JOINs
**Problem**: Model references tables not in FROM clause
```sql
-- Wrong
SELECT customers.name, orders.total 
FROM customers 
WHERE orders.status = 'completed'
```

**Solution**: Explicit JOIN requirements in prompt
```sql
-- Correct
SELECT c.name, o.total 
FROM customers c
JOIN orders o ON c.id = o.customer_id
WHERE o.status = 'completed'
```

### Issue 3: Invalid Aggregations
**Problem**: Attempting to aggregate non-numeric columns
```sql
-- Wrong
AVG(priority)  -- priority is VARCHAR ('low', 'medium', 'high')
```

**Solution**: Specify data types and valid operations
```sql
-- Correct
COUNT(CASE WHEN priority = 'high' THEN 1 END) as high_priority_count
```

## Implementation Examples

### Example 1: E-commerce Analytics (Works with most models)
```python
async def generate_ecommerce_sql(question, model):
    schema = await get_schema()
    
    if model.size >= "13B":
        # Larger models can handle this directly
        prompt = f"""
        Generate SQL for: {question}
        Tables: customers, orders, products, reviews
        """
    else:
        # Smaller models need more guidance
        prompt = f"""
        Generate SQL for: {question}
        
        Use this pattern:
        SELECT 
            c.city,
            SUM(o.total_amount) as revenue
        FROM customers c
        JOIN orders o ON c.customer_id = o.customer_id
        GROUP BY c.city
        ORDER BY revenue DESC
        """
    
    return await model.generate(prompt)
```

### Example 2: SaaS Metrics (Complex, needs templates for small models)
```python
async def generate_saas_sql(question, model):
    if model.size < "13B":
        # Small models MUST use exact template
        return SAAS_SQL_TEMPLATE
    elif model.size < "70B":
        # Medium models need structured guidance
        return generate_with_pattern(question, SAAS_PATTERN)
    else:
        # Large models handle it naturally
        return generate_direct(question, schema)
```

## Testing Your Implementation

### 1. Validate SQL Syntax
```python
async def validate_generated_sql(sql):
    try:
        # Parse SQL to check syntax
        result = await duckdb.execute(f"EXPLAIN {sql}")
        return True
    except Exception as e:
        logger.error(f"Invalid SQL: {e}")
        return False
```

### 2. Test Edge Cases
```python
test_cases = [
    "Show metrics for users with null values",
    "Calculate averages excluding outliers",
    "Complex multi-level aggregations",
    "Time-series analysis with window functions"
]
```

### 3. Benchmark Performance
```python
async def benchmark_sql_generation(model, questions):
    results = []
    for q in questions:
        start = time.time()
        sql = await generate_sql(q, model)
        valid = await validate_sql(sql)
        elapsed = time.time() - start
        
        results.append({
            "question": q,
            "time": elapsed,
            "valid": valid,
            "model": model.name
        })
    return results
```

## Best Practices

### 1. Progressive Enhancement
Start with templates for reliability, then reduce guidance as you move to larger models:

```python
def get_sql_generation_strategy(model_size):
    strategies = {
        "7B": "exact_template",
        "13B": "pattern_template", 
        "70B": "schema_guided",
        "175B+": "direct_generation"
    }
    return strategies.get(model_size, "exact_template")
```

### 2. Cache Common Queries
```python
@lru_cache(maxsize=100)
async def get_cached_sql(question_hash, model_id):
    return await generate_sql(question, model)
```

### 3. Fallback Strategies
```python
async def generate_sql_with_fallback(question, model):
    try:
        # Try direct generation first
        sql = await generate_direct(question, model)
        if await validate_sql(sql):
            return sql
    except:
        pass
    
    # Fall back to template
    return use_template(question, model)
```

### 4. Monitor and Log
```python
async def log_sql_generation(question, sql, model, success):
    await log_to_database({
        "timestamp": datetime.now(),
        "question": question,
        "sql": sql,
        "model": model.name,
        "success": success,
        "execution_time": time.elapsed()
    })
```

## Model-Specific Configurations

### Mistral 7B Configuration
```python
MISTRAL_7B_CONFIG = {
    "temperature": 0.1,  # Low for consistent SQL
    "max_tokens": 500,
    "strategy": "exact_template",
    "require_validation": True,
    "fallback_to_template": True
}
```

### GPT-4 Configuration
```python
GPT4_CONFIG = {
    "temperature": 0.3,
    "max_tokens": 1000,
    "strategy": "direct_generation",
    "require_validation": False,
    "system_prompt": "You are an expert SQL developer."
}
```

## Troubleshooting Guide

### Problem: Model returns explanations with SQL
**Solution**: Add explicit instructions
```python
prompt += "\nReturn ONLY the SQL query starting with SELECT, no explanations."
```

### Problem: Timeout on complex queries
**Solution**: Increase timeout and simplify schema
```python
config["timeout"] = 30  # seconds
config["max_tables"] = 5  # limit schema complexity
```

### Problem: Inconsistent results
**Solution**: Lower temperature and add examples
```python
config["temperature"] = 0.1
prompt += "\nExample: SELECT ... FROM ... WHERE ..."
```

## Conclusion

AI-driven SQL generation is highly dependent on model size and capabilities. While large models can generate complex SQL from natural language alone, smaller models require careful guidance through templates and examples. The SMCP-DuckDB integration demonstrates both approaches, providing a robust framework that works across the entire spectrum of model sizes.

Key takeaways:
- **Small models (7B)**: Use exact SQL templates
- **Medium models (13-70B)**: Provide patterns and guidelines
- **Large models (70B+)**: Natural language is sufficient
- **Always validate**: Check generated SQL before execution
- **Progressive enhancement**: Start strict, relax with larger models

---
**Version**: 1.0
**Last Updated**: 2025-01-14
**Author**: SMCP Development Team