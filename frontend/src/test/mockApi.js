import { AxiosError } from 'axios';
import api from '../services/api';

function parseBody(data) {
  if (typeof data !== 'string') return data; // FormData, null or undefined
  try {
    return JSON.parse(data);
  } catch {
    return data;
  }
}

function toAxiosError(config, { status, data }) {
  const response = { data, status, statusText: String(status), headers: {}, config, request: {} };
  const code = status >= 500 ? AxiosError.ERR_BAD_RESPONSE : AxiosError.ERR_BAD_REQUEST;
  return new AxiosError(`Request failed with status code ${status}`, code, config, {}, response);
}

/**
 * Replaces the HTTP adapter of the shared axios instance, so tests exercise the real
 * API client (URLs, params, bodies, interceptors) without any network access.
 *
 * `routes` maps "METHOD /path" (relative to the API base URL) to a response
 * `{ status = 200, data }`, or to a function that receives the recorded request and
 * returns such a response (or a promise of one). Unmatched requests fail as network
 * errors. Returns the array of recorded requests: `{ method, url, params, body, headers }`.
 */
export function mockApi(routes) {
  const requests = [];

  api.defaults.adapter = async (config) => {
    const method = config.method.toUpperCase();
    const request = {
      method,
      url: config.url,
      params: config.params,
      body: parseBody(config.data),
      headers: config.headers,
    };
    requests.push(request);

    const route = routes[`${method} ${config.url}`];
    if (!route) {
      throw new AxiosError(`No mock response for ${method} ${config.url}`, AxiosError.ERR_NETWORK, config);
    }

    const { status = 200, data = null } = (typeof route === 'function' ? await route(request) : route) ?? {};
    if (status >= 400) throw toAxiosError(config, { status, data });
    return { data, status, statusText: String(status), headers: {}, config, request: {} };
  };

  return requests;
}

/** Makes every request fail, so a test can never reach a real server by accident. */
export function resetApiMock() {
  api.defaults.adapter = async (config) => {
    throw new AxiosError(
      `Unexpected request in test: ${config.method?.toUpperCase()} ${config.url}`,
      AxiosError.ERR_NETWORK,
      config,
    );
  };
}

/** A promise with its resolve function exposed, for holding a response in flight. */
export function deferred() {
  let resolve;
  const promise = new Promise((done) => {
    resolve = done;
  });
  return { promise, resolve };
}
