import { clsx, type ClassValue } from 'clsx';
import { twMerge } from 'tailwind-merge';

export function cn(...inputs: ClassValue[]) {
  return twMerge(clsx(inputs));
}

export function formatCurrency(amount: number, currency: string = 'USD'): string {
  return new Intl.NumberFormat('en-US', {
    style: 'currency',
    currency,
    minimumFractionDigits: 2,
  }).format(amount);
}

export function formatTimestamp(isoString: string): string {
  try {
    const d = new Date(isoString);
    return d.toLocaleTimeString([], { hour: '2-digit', minute: '2-digit', second: '2-digit' });
  } catch {
    return isoString;
  }
}

/**
 * Safely extracts a human-readable error message from arbitrary error payloads.
 * Supports string messages, Error instances, FastAPI detail responses (string, array, or object),
 * Pydantic validation error lists, nested error objects, and provides a sensible fallback.
 * Guarantees that `[object Object]` is never returned.
 */
export function extractErrorMessage(error: unknown, fallback: string = 'An unexpected error occurred.'): string {
  if (!error) return fallback;

  // If error is already a string
  if (typeof error === 'string') {
    const trimmed = error.trim();
    if (!trimmed || trimmed === '[object Object]') {
      return fallback;
    }
    // If it is a stringified JSON object/array, parse and extract recursively
    if ((trimmed.startsWith('{') && trimmed.endsWith('}')) || (trimmed.startsWith('[') && trimmed.endsWith(']'))) {
      try {
        const parsed = JSON.parse(trimmed);
        return extractErrorMessage(parsed, fallback);
      } catch {
        return trimmed;
      }
    }
    return trimmed;
  }

  // If error is an Error instance
  if (error instanceof Error) {
    const msg = error.message ? error.message.trim() : '';
    if (msg && msg !== '[object Object]') {
      if ((msg.startsWith('{') && msg.endsWith('}')) || (msg.startsWith('[') && msg.endsWith(']'))) {
        try {
          const parsed = JSON.parse(msg);
          return extractErrorMessage(parsed, fallback);
        } catch {
          return msg;
        }
      }
      return msg;
    }
    // Check custom fields attached to error object
    const anyErr = error as any;
    if (anyErr.detail || anyErr.response || anyErr.data) {
      return extractErrorMessage(anyErr.detail || anyErr.response || anyErr.data, fallback);
    }
    return fallback;
  }

  // If error is an array (e.g. FastAPI 422 validation errors: [{ loc, msg, type }])
  if (Array.isArray(error)) {
    if (error.length === 0) return fallback;
    const parts = error
      .map((item) => {
        if (!item) return '';
        if (typeof item === 'string') return item.trim();
        if (typeof item === 'object') {
          const msg = item.msg || item.message || item.detail;
          const loc = Array.isArray(item.loc)
            ? item.loc.filter((p: any) => p !== 'body').join('.')
            : item.loc;
          if (loc && msg) return `${loc}: ${msg}`;
          if (msg) return String(msg);
          try {
            return JSON.stringify(item);
          } catch {
            return '';
          }
        }
        return String(item);
      })
      .filter((s) => s.length > 0 && s !== '[object Object]');
    return parts.length > 0 ? parts.join('; ') : fallback;
  }

  // If error is a plain object
  if (typeof error === 'object') {
    const obj = error as Record<string, any>;

    // 1. FastAPI standard HTTPException detail field
    if ('detail' in obj && obj.detail !== undefined && obj.detail !== null) {
      const detailMsg = extractErrorMessage(obj.detail, '');
      if (detailMsg && detailMsg !== '[object Object]') {
        return detailMsg;
      }
    }

    // 2. Direct string message / msg fields
    if (typeof obj.message === 'string' && obj.message.trim() && obj.message !== '[object Object]') {
      return obj.message.trim();
    }
    if (typeof obj.msg === 'string' && obj.msg.trim() && obj.msg !== '[object Object]') {
      return obj.msg.trim();
    }

    // 3. Error code / name combined with message or guidance
    if (typeof obj.error === 'string' && obj.error.trim() && obj.error !== '[object Object]') {
      const errorName = obj.error.trim();
      const subMsg =
        typeof obj.message === 'string' && obj.message.trim() && obj.message !== '[object Object]'
          ? obj.message.trim()
          : '';
      return subMsg ? `${errorName}: ${subMsg}` : errorName;
    }

    // 4. Nested error object
    if (obj.error && typeof obj.error === 'object') {
      const nested = extractErrorMessage(obj.error, '');
      if (nested && nested !== '[object Object]') {
        return nested;
      }
    }

    // 5. Setup guidance
    if (typeof obj.setup_guidance === 'string' && obj.setup_guidance.trim()) {
      return obj.setup_guidance.trim();
    }

    // 6. Safe JSON stringify fallback (avoiding [object Object])
    try {
      const str = JSON.stringify(obj);
      if (str && str !== '{}') {
        return str;
      }
    } catch {
      // ignore
    }
  }

  return fallback;
}
