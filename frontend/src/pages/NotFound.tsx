/** Fallback page for unknown routes. */

import { Button } from "../components/ui/Button";
import { EmptyState } from "../components/ui/EmptyState";

export function NotFound() {
  return (
    <div className="flex flex-1 items-center justify-center px-4">
      <EmptyState
        icon="alert"
        title="Page not found"
        description="That route doesn't exist in this app."
        action={
          <Button to="/" variant="secondary">
            Back to home
          </Button>
        }
      />
    </div>
  );
}
