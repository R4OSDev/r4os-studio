# Studio connections

Studio owns your conversation, history, tool permissions, skills, context,
Goal, queue and recovery. A connection supplies model access and its account
limits. Changing the selected model does not create another conversation.

## OpenAI subscription

1. Open System → LLM Provider → New Provider.
2. Choose **OpenAI · ChatGPT subscription**, enter a name and add the connection.
3. Select **Continue with ChatGPT** and open the OpenAI sign-in page.
4. Choose the account and workspace at OpenAI. Copy the complete final redirect
   address and paste it into Studio, then select **Complete sign-in**. The final
   localhost page may fail to open on another computer; copy its address anyway.
5. Wait for **Connected**. No browser helper, desktop download or terminal is
   required. This one sign-in supplies model access and subscription limits.
6. If **Use this connection in Studio** appears, select it. Refresh **Models**
   to read the account's catalog. This check does not send a model message.
7. Select the connection and model when creating a Studio session.

The provider row, account details and session settings use the same reported
limits. Missing or old values stay unavailable. Included windows, reset times,
credit balances and earned resets are separate facts; viewing them changes no
spending setting and uses no reset. A reset requires its existing explicit
confirmation and is bound to the displayed sign-in.

To change account or workspace, disconnect and sign in again. Disconnecting
removes this connection's local sign-in after its original workers end; it does
not claim remote token revocation. Other connections keep their own sign-ins.
The older **ChatGPT plan · Direct registration** is a separate access method,
with its own usage reporting; it is not the native subscription connection.

## Existing conversations and provider changes

Installing an update, opening a session or signing in never converts a saved
conversation or starts work. For a native conversation, open Session settings
→ Conversation, choose a Studio connection, review the conversion and confirm
it explicitly. Original messages and confirmed effects stay available under
the same session identity.

After conversion, choose another connection/model in ordinary session settings.
Finish or cancel accepted queued inputs first: they keep their original frozen
selection. Studio retains original model responses, visible history, complete
tool observations, checkpoints and Goal accounting. Private model payloads are
not forwarded to an incompatible connection, and historical tool effects are
not executed again to reconstruct the conversation.

## Available connection types

OpenAI subscription, direct ChatGPT registration, Z.AI Coding Plan, OpenRouter,
Custom API and Local API model connections use the common Studio runtime.
They retain their own authentication, protocol and actual account limits.
Configure API keys and endpoints through the browser. Studio never chooses a
paid replacement account or another model implicitly.

Claude subscriptions currently use explicitly labelled native conversations.
A conforming model-only subscription connection is still unavailable; the
native agent is not presented as a common Studio model connector. An independent
Messages API connection uses the common runtime when you explicitly configure
its account and billing. No such independent live account was available in
this release qualification. A missing native feature or an unavailable free
endpoint remains visible as a limitation.
