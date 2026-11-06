import {sha256} from './json-sha256';
self.onmessage=(event:MessageEvent<ArrayBuffer>)=>{self.postMessage(sha256(new Uint8Array(event.data)));};
