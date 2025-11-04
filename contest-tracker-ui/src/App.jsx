import React, { useState, useEffect } from 'react';
import { Check, Loader, LogIn, LogOut, RefreshCw } from 'lucide-react';

// Get the backend URL from environment variables
// In local dev, this will be http://localhost:5000
// In Render, it will be https://your-app-name.onrender.com
const API_URL = import.meta.env.VITE_API_URL || 'http://localhost:5000';

// --- DEBUG PRINT ---
console.log(`React App Loaded. Using API_URL: ${API_URL}`);
// --- END DEBUG PRINT ---

// --- NEW: API Helper ---
// We use 'credentials: "include"' to send the session cookie
const api = {
  get: (path) => fetch(`${API_URL}${path}`, {
    method: 'GET',
    credentials: 'include',
  }),
  post: (path) => fetch(`${API_URL}${path}`, {
    method: 'POST',
    credentials: 'include',
  }),
};

export default function App() {
  const [auth, setAuth] = useState({
    isLoading: true,
    isLoggedIn: false,
    userEmail: null,
  });
  const [sync, setSync] = useState({
    isLoading: false,
    isComplete: false,
    message: '',
    newContests: [],
  });

  // --- NEW: Check auth status on page load ---
  useEffect(() => {
    const checkUserAuth = async () => {
      try {
        const res = await api.get('/check-auth');
        if (res.ok) {
          const data = await res.json();
          setAuth({
            isLoading: false,
            isLoggedIn: true,
            userEmail: data.user.email,
          });
        } else {
          setAuth({ isLoading: false, isLoggedIn: false, userEmail: null });
        }
      } catch (error) {
        console.error('Auth check failed:', error);
        setAuth({ isLoading: false, isLoggedIn: false, userEmail: null });
      }
    };
    checkUserAuth();
  }, []);

  // --- NEW: This is now a POST to / (manual_sync) ---
  const handleSync = async () => {
    setSync({ ...sync, isLoading: true, isComplete: false });
    try {
      const res = await api.post('/');
      const data = await res.json();

      if (!res.ok) {
        throw new Error(data.error || 'Sync failed');
      }

      setSync({
        isLoading: false,
        isComplete: true,
        message: data.message,
        newContests: data.new_contests || [],
      });
    } catch (error) {
      console.error('Sync failed:', error);
      setSync({
        isLoading: false,
        isComplete: false,
        message: `Sync failed: ${error.message}. If you see an auth error, please log out and log in again.`,
        newContests: [],
      });
    }
  };

  // --- NEW: Logout function ---
  const handleLogout = async () => {
    await api.post('/logout');
    setAuth({ isLoading: false, isLoggedIn: false, userEmail: null });
    setSync({ isLoading: false, isComplete: false, message: '', newContests: [] });
  };

  return (
    <div className="font-sans text-white bg-gray-900 min-h-screen flex items-center justify-center p-4">
      <div
        className="absolute inset-0 z-0"
        style={{
          backgroundImage:
            'radial-gradient(circle at 25% 25%, rgba(59, 130, 246, 0.15), rgba(59, 130, 246, 0) 50%), radial-gradient(circle at 75% 75%, rgba(139, 92, 246, 0.15), rgba(139, 92, 246, 0) 50%)',
        }}
      ></div>

      <div className="w-full max-w-md bg-white/5 backdrop-blur-xl rounded-2xl shadow-2xl p-8 z-10 border border-white/10">
        <header className="flex justify-between items-center mb-6">
          <h1 className="text-2xl font-bold text-transparent bg-clip-text bg-gradient-to-r from-blue-400 to-purple-500">
            Contest Sync
          </h1>
          {auth.isLoggedIn && (
            <button
              onClick={handleLogout}
              className="text-sm text-gray-400 hover:text-white transition-colors flex items-center"
            >
              <LogOut className="w-4 h-4 mr-1.5" />
              Logout
            </button>
          )}
        </header>

        {auth.isLoading && <AuthLoader />}

        {!auth.isLoading && !auth.isLoggedIn && (
          <LoginView />
        )}

        {!auth.isLoading && auth.isLoggedIn && (
          <SyncView
            auth={auth}
            sync={sync}
            onSync={handleSync}
          />
        )}
      </div>
    </div>
  );
}

// --- NEW: Login Component ---
function LoginView() {
  return (
    <div>
      <h2 className="text-lg font-semibold text-gray-200 mb-2">
        Welcome!
      </h2>
      <p className="text-gray-400 mb-6">
        Log in with your Google Account to automatically sync coding contests to
        your Google Calendar.
      </p>
      <a
        href={`${API_URL}/login`}
        className="w-full flex items-center justify-center bg-blue-600 hover:bg-blue-500 text-white font-semibold py-3 px-4 rounded-lg transition-all duration-300 shadow-lg shadow-blue-600/30"
      >
        <LogIn className="w-5 h-5 mr-2.5" />
        Sign in with Google
      </a>
    </div>
  );
}

// --- NEW: Main Sync Component ---
function SyncView({ auth, sync, onSync }) {
  return (
    <div>
      <p className="text-gray-300 mb-6">
        Logged in as <strong className="font-medium text-white">{auth.userEmail}</strong>.
      </p>
      
      {!sync.isLoading && (
        <button
          onClick={onSync}
          className="w-full flex items-center justify-center bg-blue-600 hover:bg-blue-500 text-white font-semibold py-3 px-4 rounded-lg transition-all duration-300 shadow-lg shadow-blue-600/30"
        >
          <RefreshCw className="w-5 h-5 mr-2.5" />
          Sync My Contests Manually
        </button>
      )}

      {sync.isLoading && (
        <div className="flex flex-col items-center justify-center text-center p-4">
          <Loader className="w-12 h-12 text-blue-400 animate-spin" />
          <p className="text-lg font-semibold text-gray-200 mt-4">Syncing...</p>
          <p className="text-gray-400">
            Fetching contests and updating your calendar.
          </p>
        </div>
      )}

      {sync.isComplete && (
        <div className="mt-6 p-4 bg-white/5 rounded-lg border border-white/10">
          <div className="flex items-center">
            <Check className="w-6 h-6 text-green-400" />
            <h3 className="text-lg font-semibold text-green-400 ml-2">Sync Complete!</h3>
          </div>
          <p className="text-gray-300 mt-2">{sync.message}</p>
          {sync.newContests.length > 0 && (
            <div className="mt-3 pt-3 border-t border-white/10">
              <h4 className="font-semibold text-gray-200 mb-2">New Contests Added:</h4>
              <ul className="space-y-1 max-h-32 overflow-y-auto">
                {sync.newContests.map((contest, i) => (
                  <li key={i} className="text-sm text-gray-400 truncate">
                    {contest.platform}: {contest.title}
                  </li>
                ))}
              </ul>
            </div>
          )}
        </div>
      )}

      {sync.message && !sync.isComplete && !sync.isLoading && (
         <div className="mt-6 p-4 bg-red-900/20 rounded-lg border border-red-500/30">
           <p className="text-red-300">{sync.message}</p>
         </div>
      )}
      
      <p className="text-xs text-gray-500 text-center mt-6">
        Your contests will also be synced periodically in the background.
      </CORS(app, supports_credentials=True, resources={r"/*": {"origins": "*"}})>
    </div>
  );
}

// --- NEW: Loading Spinner ---
function AuthLoader() {
  return (
    <div className="flex flex-col items-center justify-center text-center p-8">
      <Loader className="w-12 h-12 text-blue-400 animate-spin" />
      <p className="text-lg font-semibold text-gray-200 mt-4">
        Checking authentication...
      </CORS(app, supports_credentials=True, resources={r"/*": {"origins": "*"}})
    </div>
  );
}

