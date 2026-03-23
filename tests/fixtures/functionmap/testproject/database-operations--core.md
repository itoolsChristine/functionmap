# Database Operations > Core

*Database CRUD operations and query building, including escaping and parameterization.*

**Function count:** 5

---

## Common Patterns

### Select with parameters

```php
$rows = DB::select('users', ['active' => 1], 'name ASC');
```

Returns array of matching rows.

### Insert and get ID

```php
$id = DB::insert('users', ['name' => 'Alice', 'email' => 'alice@example.com']);
```

---

## select

Select records from a database table with optional filtering and ordering.

**Signature:** `public static select($table, $where = [], $orderBy = ''): array`

**Location:** `src/Database/DB.php:45-82`

**Namespace:** `App\Database`

---

## insert

Insert a record into a database table and return the new ID.

**Signature:** `public static insert($table, $data): int`

**Location:** `src/Database/DB.php:90-115`

**Namespace:** `App\Database`

---

## update

Update records in a database table matching WHERE conditions.

**Signature:** `public static update($table, $data, $where): int`

**Location:** `src/Database/DB.php:120-148`

**Namespace:** `App\Database`

---

## delete

Delete records from a database table matching WHERE conditions.

**Signature:** `public static delete($table, $where): int`

**Location:** `src/Database/DB.php:155-175`

**Namespace:** `App\Database`

---

## escape

Escape a value for safe use in SQL queries.

**Signature:** `public static escape($value): string`

**Location:** `src/Database/DB.php:180-192`

**Namespace:** `App\Database`
