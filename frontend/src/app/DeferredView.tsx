import { Component, createContext, createElement, lazy, Suspense, useContext } from 'react';
import type { ComponentProps, ComponentType, ReactNode } from 'react';

// Navigation and its leave guards stay mounted while a view downloads or fails.
export const ViewRecovery = createContext(() => window.location.reload());
function UnavailableView({ dismiss }: { dismiss?: () => void }) {
  const reload = useContext(ViewRecovery);
  return <div className="view-status" role="alert"><p>This view could not be loaded.</p>
    <button type="button" onClick={reload}>Reload Studio</button>{dismiss && <button type="button" onClick={dismiss}>Close</button>}</div>;
}
class ViewBoundary extends Component<{ children: ReactNode; dismiss?: () => void }, { failed: boolean }> {
  state = { failed: false };
  static getDerivedStateFromError() { return { failed: true }; }
  render() { return this.state.failed ? <UnavailableView dismiss={this.props.dismiss} /> : this.props.children; }
}

// eslint-disable-next-line @typescript-eslint/no-explicit-any -- Match React.lazy's component constraint while retaining each view's exact props.
export function deferView<ViewType extends ComponentType<any>>(load: () => Promise<{ default: ViewType }>, dismiss?: (props: ComponentProps<ViewType>) => void) {
  const View = lazy(load);
  return function DeferredView(props: ComponentProps<ViewType>) {
    // The public signature above validates props; pass them through unchanged.
    const close = dismiss ? () => dismiss(props) : undefined;
    return <ViewBoundary dismiss={close}><Suspense fallback={<div className="view-status" role="status"><p>Loading view…</p>{close && <button type="button" onClick={close}>Cancel</button>}</div>}>{createElement(View, props as never)}</Suspense></ViewBoundary>;
  };
}
