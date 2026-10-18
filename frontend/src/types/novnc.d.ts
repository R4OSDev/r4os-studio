// noVNC 1.7 exports the ES module at the package root. The maintained 1.6
// public API types still use the former lib/rfb import path.
declare module '@novnc/novnc' {
  import RFB from '@novnc/novnc/lib/rfb';
  export default RFB;
}
