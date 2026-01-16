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

type ScrollPos =
  | 'top'
  | 'bottom'
  | 'left'
  | 'right'
  | 'topleft'
  | 'topright'
  | 'bottomleft'
  | 'bottomright'
  | 'center';

interface ScrollToOptionsEx {
  behavior?: ScrollBehavior; // 'auto' | 'smooth'
  offsetX?: number; // 目標 X 方向額外位移（正=向右）
  offsetY?: number; // 目標 Y 方向額外位移（正=向下）
}

export function scrollToWindow(pos: string, opts: ScrollToOptionsEx = {}) {
  const p = (pos || '').replace(/\s+/g, '').toLowerCase() as ScrollPos;
  const { behavior = 'smooth', offsetX = 0, offsetY = 0 } = opts;

  // 取得頁面可視大小與可滾動範圍
  const docEl = document.documentElement;
  const body = document.body;

  // 內容總寬高（包含可滾動區域）
  const fullWidth = Math.max(
    body.scrollWidth,
    docEl.scrollWidth,
    body.offsetWidth,
    docEl.offsetWidth,
    body.clientWidth,
    docEl.clientWidth,
  );
  const fullHeight = Math.max(
    body.scrollHeight,
    docEl.scrollHeight,
    body.offsetHeight,
    docEl.offsetHeight,
    body.clientHeight,
    docEl.clientHeight,
  );

  // 畫面可視區域
  const viewW = window.innerWidth || docEl.clientWidth;
  const viewH = window.innerHeight || docEl.clientHeight;

  // 目標座標預設為目前位置
  let x = window.scrollX || window.pageXOffset || 0;
  let y = window.scrollY || window.pageYOffset || 0;

  // 計算各方位的目標座標
  const edge = {
    left: 0,
    right: Math.max(0, fullWidth - viewW),
    top: 0,
    bottom: Math.max(0, fullHeight - viewH),
    centerX: Math.max(0, Math.round((fullWidth - viewW) / 2)),
    centerY: Math.max(0, Math.round((fullHeight - viewH) / 2)),
  };

  switch (p) {
    case 'top':
      y = edge.top;
      break;

    case 'bottom':
      y = edge.bottom;
      break;

    case 'left':
      x = edge.left;
      break;

    case 'right':
      x = edge.right;
      break;

    case 'topleft':
      x = edge.left;
      y = edge.top;
      break;

    case 'topright':
      x = edge.right;
      y = edge.top;
      break;

    case 'bottomleft':
      x = edge.left;
      y = edge.bottom;
      break;

    case 'bottomright':
      x = edge.right;
      y = edge.bottom;
      break;
  }

  // 套用額外位移（可用於微調）
  x = Math.max(0, x + offsetX);
  y = Math.max(0, y + offsetY);

  window.scrollTo({ left: x, top: y, behavior });
  // 可選：除錯訊息
  // console.log(`scroll to ${p}: (${x}, ${y})`)
}
