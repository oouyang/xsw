import { useAppConfig } from 'src/services/useAppConfig';

export function is_production() {
  return process.env.NODE_ENV === 'production';
}

const { update, config } = useAppConfig();
export function toggleAppFeatures(key: string) {
  update({ featureFlags: { [key]: !config.value.featureFlags[key] } });
}

export function getCurrentUser() {
  const me = JSON.parse(config.value?.me || '{"name":"unknown"}');
  return me && typeof me.name === 'string' ? me.name : 'unknown';
}
export function alog(...args: unknown[]): void {
  const timestamp = `[${new Date().toLocaleString()}] :`;
  console.log(timestamp, ...args);
}
