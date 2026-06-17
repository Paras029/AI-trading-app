import { Outlet } from "react-router-dom";
import { Sidebar } from "./Sidebar";
import { useStore } from "../../store";

export function Layout() {
  const { notification, setNotification } = useStore();

  return (
    <div className="flex flex-col min-h-screen bg-cream font-sans">
      <div className="flex flex-1 overflow-hidden">
        <Sidebar />
        <main className="flex-1 flex flex-col overflow-auto">
          {notification && (
            <div className="bg-amber-50 border-b border-amber-200 px-6 py-2 flex items-center justify-between shrink-0">
              <div className="flex items-center gap-2 text-sm text-amber-800">
                <span className="text-base">🎯</span>
                {notification}
              </div>
              <button
                onClick={() => setNotification(null)}
                className="text-amber-500 hover:text-amber-700 text-lg leading-none ml-4"
              >
                ×
              </button>
            </div>
          )}
          <div className="flex-1 p-6 overflow-auto">
            <Outlet />
          </div>
        </main>
      </div>
    </div>
  );
}
