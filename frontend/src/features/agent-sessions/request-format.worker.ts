import {formatRequest} from './request-format';
self.onmessage=(event:MessageEvent<string>)=>self.postMessage(formatRequest(event.data));
