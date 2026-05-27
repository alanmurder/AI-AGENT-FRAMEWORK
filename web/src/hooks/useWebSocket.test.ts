import { describe, expect, test } from 'vitest';
import { isGatewayAuthError } from './useWebSocket';

describe('isGatewayAuthError', () => {
  test('does not treat model provider authentication errors as app auth failures', () => {
    expect(isGatewayAuthError({
      type: 'error',
      content: "Error code: 401 - {'error': {'message': 'Authentication Fails', 'type': 'authentication_error'}}",
    })).toBe(false);
  });

  test('treats gateway invalid authentication errors as app auth failures', () => {
    expect(isGatewayAuthError({
      type: 'error',
      content: '401: Invalid or missing authentication',
    })).toBe(true);
  });
});
