export class ChatFault extends Error {
  constructor(code = 'chat_protocol_error') { super(code); this.code = code; }
}
