/**
 * Retry utility for handling failed operations with exponential backoff
 */

export interface RetryOptions {
  maxAttempts?: number;
  baseDelay?: number;
  maxDelay?: number;
  backoffFactor?: number;
  retryCondition?: (error: any) => boolean;
}

export interface RetryResult<T> {
  success: boolean;
  data?: T;
  error?: any;
  attempts: number;
}

/**
 * Default retry condition - retry on network errors and 5xx server errors
 */
const defaultRetryCondition = (error: any): boolean => {
  // Retry on network errors
  if (error.error?.code === 'NETWORK_ERROR' || error.error?.code === 'TIMEOUT') {
    return true;
  }
  
  // Retry on 5xx server errors
  if (error.response?.status >= 500) {
    return true;
  }
  
  // Retry on specific error codes
  const retryableCodes = [
    'SERVICE_UNAVAILABLE',
    'GATEWAY_TIMEOUT',
    'BAD_GATEWAY',
    'INTERNAL_SERVER_ERROR'
  ];
  
  if (error.error?.code && retryableCodes.includes(error.error.code)) {
    return true;
  }
  
  return false;
};

/**
 * Retry an async operation with exponential backoff
 */
export async function retryOperation<T>(
  operation: () => Promise<T>,
  options: RetryOptions = {}
): Promise<RetryResult<T>> {
  const {
    maxAttempts = 3,
    baseDelay = 1000,
    maxDelay = 10000,
    backoffFactor = 2,
    retryCondition = defaultRetryCondition
  } = options;

  let lastError: any;
  
  for (let attempt = 1; attempt <= maxAttempts; attempt++) {
    try {
      const result = await operation();
      return {
        success: true,
        data: result,
        attempts: attempt
      };
    } catch (error) {
      lastError = error;
      
      // Don't retry if this is the last attempt
      if (attempt === maxAttempts) {
        break;
      }
      
      // Check if we should retry this error
      if (!retryCondition(error)) {
        break;
      }
      
      // Calculate delay with exponential backoff
      const delay = Math.min(
        baseDelay * Math.pow(backoffFactor, attempt - 1),
        maxDelay
      );
      
      console.warn(`Operation failed (attempt ${attempt}/${maxAttempts}), retrying in ${delay}ms:`, error);
      
      // Wait before retrying
      await new Promise(resolve => setTimeout(resolve, delay));
    }
  }
  
  return {
    success: false,
    error: lastError,
    attempts: maxAttempts
  };
}

/**
 * Create a retry wrapper for a function
 */
export function withRetry<T extends (...args: any[]) => Promise<any>>(
  fn: T,
  options: RetryOptions = {}
): T {
  return ((...args: Parameters<T>) => {
    return retryOperation(() => fn(...args), options);
  }) as T;
}

/**
 * Retry-enabled API client wrapper
 */
export class RetryableApiClient {
  private defaultOptions: RetryOptions;
  
  constructor(defaultOptions: RetryOptions = {}) {
    this.defaultOptions = {
      maxAttempts: 3,
      baseDelay: 1000,
      maxDelay: 10000,
      backoffFactor: 2,
      retryCondition: defaultRetryCondition,
      ...defaultOptions
    };
  }
  
  async execute<T>(
    operation: () => Promise<T>,
    options?: RetryOptions
  ): Promise<T> {
    const mergedOptions = { ...this.defaultOptions, ...options };
    const result = await retryOperation(operation, mergedOptions);
    
    if (result.success) {
      return result.data!;
    } else {
      throw result.error;
    }
  }
}

/**
 * Exponential backoff delay calculator
 */
export function calculateBackoffDelay(
  attempt: number,
  baseDelay: number = 1000,
  maxDelay: number = 10000,
  backoffFactor: number = 2
): number {
  return Math.min(
    baseDelay * Math.pow(backoffFactor, attempt - 1),
    maxDelay
  );
}

/**
 * Jittered exponential backoff (adds randomness to prevent thundering herd)
 */
export function calculateJitteredBackoffDelay(
  attempt: number,
  baseDelay: number = 1000,
  maxDelay: number = 10000,
  backoffFactor: number = 2,
  jitterFactor: number = 0.1
): number {
  const baseBackoff = calculateBackoffDelay(attempt, baseDelay, maxDelay, backoffFactor);
  const jitter = baseBackoff * jitterFactor * (Math.random() * 2 - 1); // Random between -jitterFactor and +jitterFactor
  return Math.max(0, baseBackoff + jitter);
}