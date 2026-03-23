# String Utilities > Core

*String formatting, transformation, and display helpers for both PHP and JavaScript.*

**Function count:** 5

---

## Common Patterns

### Format currency

```php
$price = formatCurrency(29.99, 'USD');
```

Returns '$29.99'.

---

## formatCurrency

Format a numeric amount as a currency string with symbol and decimals.

**Signature:** `formatCurrency($amount, $currency = 'USD'): string`

**Location:** `src/Helpers/strings.php:10-25`

---

## slugify

Convert a string to a URL-safe slug.

**Signature:** `slugify($text): string`

**Location:** `src/Helpers/strings.php:30-42`

---

## truncate

Truncate a string to a maximum length with optional suffix.

**Signature:** `truncate($text, $maxLength = 100, $suffix = '...'): string`

**Location:** `src/Helpers/strings.php:48-60`

---

## debounce

Create a debounced version of a function that delays invocation.

**Signature:** `debounce(fn, delay): function`

**Location:** `assets/js/utils.js:5-18`

---

## formatDate

Format a Date object into a human-readable string.

**Signature:** `formatDate(date, format): string`

**Location:** `assets/js/utils.js:25-45`
