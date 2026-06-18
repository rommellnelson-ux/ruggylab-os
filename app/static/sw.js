// Service Worker for RuggyLab OS - Offline functionality
const CACHE_NAME = 'ruggylab-os-v2';
const STATIC_CACHE = 'ruggylab-static-v2';
const API_CACHE = 'ruggylab-api-v2';

// Static assets to cache
const STATIC_ASSETS = [
  '/app',
  '/app/express',
  '/static/ai/training_data_manager.js',
  '/static/ai/malaria_dataset_collector.js',
  '/static/sw.js'
];

// API endpoints to cache with specific strategies
const API_CACHE_ROUTES = {
  // Cache first for patient data
  '/api/v1/patients': 'cacheFirst',
  '/api/v1/samples': 'cacheFirst',
  '/api/v1/results': 'cacheFirst',
  '/api/v1/reagents': 'cacheFirst',
  
  // Network first for critical data
  '/api/v1/reports/epidemiology-summary': 'networkFirst',
  '/api/v1/reports/stock-dashboard': 'networkFirst',
  
  // Network only for actions
  '/api/v1/login/access-token': 'networkOnly',
  '/api/v1/patients': 'networkOnly',
  '/api/v1/samples': 'networkOnly',
  '/api/v1/results': 'networkOnly',
  '/api/v1/reagents': 'networkOnly'
};

// Install event - cache static assets
self.addEventListener('install', (event) => {
  console.log('Service Worker installing...');
  event.waitUntil(
    caches.open(STATIC_CACHE)
      .then((cache) => {
        console.log('Caching static assets');
        return cache.addAll(STATIC_ASSETS);
      })
      .then(() => self.skipWaiting())
  );
});

// Activate event - clean up old caches
self.addEventListener('activate', (event) => {
  console.log('Service Worker activating...');
  event.waitUntil(
    caches.keys()
      .then((cacheNames) => {
        return Promise.all(
          cacheNames.map((cacheName) => {
            if (cacheName !== STATIC_CACHE && cacheName !== API_CACHE) {
              console.log('Deleting old cache:', cacheName);
              return caches.delete(cacheName);
            }
          })
        );
      })
      .then(() => self.clients.claim())
  );
});

// Fetch event - implement caching strategies
self.addEventListener('fetch', (event) => {
  const { request } = event;
  const url = new URL(request.url);
  
  // Skip non-HTTP requests
  if (!request.url.startsWith('http')) {
    return;
  }
  
  // API requests
  if (url.pathname.startsWith('/api/')) {
    event.respondWith(handleApiRequest(request));
    return;
  }
  
  // Static assets
  if (STATIC_ASSETS.some(asset => request.url.includes(asset))) {
    event.respondWith(handleStaticRequest(request));
    return;
  }
  
  // HTML pages - cache first
  if (request.destination === 'document') {
    event.respondWith(handleDocumentRequest(request));
    return;
  }
});

// Handle API requests with different strategies
async function handleApiRequest(request) {
  const url = new URL(request.url);
  const method = request.method;
  
  // Determine strategy based on route and method
  let strategy = 'networkFirst';
  
  // Check exact matches first
  if (API_CACHE_ROUTES[url.pathname]) {
    strategy = API_CACHE_ROUTES[url.pathname];
  } else {
    // Check pattern matches
    for (const [route, routeStrategy] of Object.entries(API_CACHE_ROUTES)) {
      if (url.pathname.startsWith(route)) {
        strategy = routeStrategy;
        break;
      }
    }
  }
  
  // Force network only for write operations
  if (method !== 'GET') {
    strategy = 'networkOnly';
  }
  
  switch (strategy) {
    case 'cacheFirst':
      return cacheFirst(request);
    case 'networkFirst':
      return networkFirst(request);
    case 'networkOnly':
      return networkOnly(request);
    default:
      return networkFirst(request);
  }
}

// Cache first strategy
async function cacheFirst(request) {
  const cachedResponse = await caches.match(request);
  
  if (cachedResponse) {
    // Update cache in background
    fetch(request).then((response) => {
      if (response.ok) {
        caches.open(API_CACHE).then((apiCache) => apiCache.put(request, response.clone()));
      }
    }).catch(() => {
      // Ignore network errors for cache first
    });
    
    return cachedResponse;
  }
  
  // Fallback to network
  try {
    const networkResponse = await fetch(request);
    
    if (networkResponse.ok) {
      const apiCache = await caches.open(API_CACHE);
      apiCache.put(request, networkResponse.clone());
    }
    
    return networkResponse;
  } catch (error) {
    // Return offline response for API requests
    return new Response(
      JSON.stringify({ 
        error: 'Offline - Données en cache uniquement', 
        offline: true 
      }),
      {
        status: 503,
        headers: { 'Content-Type': 'application/json' }
      }
    );
  }
}

// Network first strategy
async function networkFirst(request) {
  try {
    const networkResponse = await fetch(request);
    
    if (networkResponse.ok) {
      const apiCache = await caches.open(API_CACHE);
      apiCache.put(request, networkResponse.clone());
    }
    
    return networkResponse;
  } catch (error) {
    // Fallback to cache
    const cachedResponse = await caches.match(request);
    
    if (cachedResponse) {
      return cachedResponse;
    }
    
    // Return offline response
    return new Response(
      JSON.stringify({ 
        error: 'Hors ligne et aucune donnée en cache', 
        offline: true 
      }),
      {
        status: 503,
        headers: { 'Content-Type': 'application/json' }
      }
    );
  }
}

// Network only strategy
async function networkOnly(request) {
  try {
    return await fetch(request);
  } catch (error) {
    return new Response(
      JSON.stringify({ 
        error: 'Connexion requise pour cette action', 
        offline: true 
      }),
      {
        status: 503,
        headers: { 'Content-Type': 'application/json' }
      }
    );
  }
}

// Handle static requests
async function handleStaticRequest(request) {
  const cachedResponse = await caches.match(request);
  
  if (cachedResponse) {
    return cachedResponse;
  }
  
  try {
    const networkResponse = await fetch(request);
    
    if (networkResponse.ok) {
      const staticCache = await caches.open(STATIC_CACHE);
      staticCache.put(request, networkResponse.clone());
    }
    
    return networkResponse;
  } catch (error) {
    // Return offline page for documents
    if (request.destination === 'document') {
      return caches.match('/') || new Response('Offline', { status: 503 });
    }
    
    return new Response('Resource not available offline', { status: 503 });
  }
}

// Handle document requests
async function handleDocumentRequest(request) {
  const cachedResponse = await caches.match(request);
  
  if (cachedResponse) {
    return cachedResponse;
  }
  
  try {
    const networkResponse = await fetch(request);
    
    if (networkResponse.ok) {
      const staticCache = await caches.open(STATIC_CACHE);
      staticCache.put(request, networkResponse.clone());
    }
    
    return networkResponse;
  } catch (error) {
    return caches.match('/') || new Response('Offline', { status: 503 });
  }
}
