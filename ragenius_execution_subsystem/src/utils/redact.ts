const REDACT_KEYS = new Set([
  "authorization",
  "cookie",
  "set-cookie",
  "api_key",
  "apikey",
  "access_token",
  "refresh_token",
  "password",
  "secret",
  "private_key"
]);

function shouldRedact(key: string, value: unknown): boolean {
  const normalizedKey = key.toLowerCase();
  if (REDACT_KEYS.has(normalizedKey)) {
    return true;
  }

  return (
    typeof value === "string" &&
    value.toLowerCase().includes("bearer ")
  );
}

export function redactSensitiveValue<T>(value: T): T {
  if (Array.isArray(value)) {
    return value.map((item) => redactSensitiveValue(item)) as T;
  }

  if (value && typeof value === "object") {
    return Object.fromEntries(
      Object.entries(value).map(([key, nestedValue]) => [
        key,
        shouldRedact(key, nestedValue)
          ? "[REDACTED]"
          : redactSensitiveValue(nestedValue)
      ])
    ) as T;
  }

  return value;
}
