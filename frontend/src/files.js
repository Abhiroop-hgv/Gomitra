export function fileToDataURL(file, maxSide) {
  return new Promise((resolve, reject) => {
    const fr = new FileReader();
    fr.onerror = reject;
    fr.onload = () => {
      const im = new Image();
      im.onerror = reject;
      im.onload = () => {
        const s = Math.min(1, (maxSide || 1280) / Math.max(im.width, im.height));
        const c = document.createElement('canvas');
        c.width = Math.round(im.width * s); c.height = Math.round(im.height * s);
        c.getContext('2d').drawImage(im, 0, 0, c.width, c.height);
        resolve(c.toDataURL('image/jpeg', 0.85));
      };
      im.src = fr.result;
    };
    fr.readAsDataURL(file);
  });
}
export function framesFromVideo(file, n) {
  return new Promise((resolve, reject) => {
    const v = document.createElement('video'); v.muted = true; v.playsInline = true; v.preload = 'auto'; v.src = URL.createObjectURL(file);
    v.onerror = () => reject(new Error('video'));
    v.onloadedmetadata = async () => {
      const dur = isFinite(v.duration) && v.duration > 0 ? v.duration : 3, out = [];
      const step = Math.max(0.5, Math.min(0.8, dur / (n + 1))), start = Math.max(0, (dur - step * (n - 1)) / 2);
      try {
        for (let i = 0; i < n; i++) {
          const seeked = new Promise((r) => { v.onseeked = r; });
          v.currentTime = Math.min(Math.max(0, dur - 0.05), start + i * step); await seeked;
          const sc = Math.min(1, 960 / Math.max(v.videoWidth, v.videoHeight)), c = document.createElement('canvas');
          c.width = Math.round(v.videoWidth * sc); c.height = Math.round(v.videoHeight * sc);
          c.getContext('2d').drawImage(v, 0, 0, c.width, c.height); out.push(c.toDataURL('image/jpeg', 0.85));
        }
        URL.revokeObjectURL(v.src); resolve(out);
      } catch (e) { reject(e); }
    };
  });
}
export function bufToB64(buf) {
  const b = new Uint8Array(buf); let s = '';
  for (let i = 0; i < b.length; i += 0x8000) s += String.fromCharCode.apply(null, b.subarray(i, i + 0x8000));
  return btoa(s);
}
export async function urlToDataURL(url, maxSide) { const b = await (await fetch(url)).blob(); return fileToDataURL(b, maxSide); }
