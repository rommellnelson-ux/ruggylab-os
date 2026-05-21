// RuggyLab OS - Service Worker
// Gestion du mode hors-ligne et synchronisation background

const CACHE_NAME = 'ruggylab-v1';
const STATIC_ASSETS = [
  '/app/express',
  '/app',
  '/static/ai/training_data_manager.js',
  '/static/ai/malaria_dataset_collector.js',
  '/static/sw.js'
];

// Installation - mise en cache des assets essentiels
self.addEventListener('install', (event) => {
  event.waitUntil(
    caches.open(CACHE_NAME).then((cache) => {
      return cache.addAll(STATIC_ASSETS);
    })
  );
  self.skipWaiting();
});

// Activation - nettoyage des anciens caches
self.addEventListener('activate', (event) => {
  event.waitUntil(
    caches.keys().then((cacheNames) => {
      return Promise.all(
        cacheNames
          .filter((name) => name !== CACHE_NAME)
          .map((name) => caches.delete(name))
      );
    })
  );
  self.clients.claim();
});

// Stratégie de cache : Network First avec fallback cache
self.addEventListener('fetch', (event) => {
  // Ignorer les requêtes API POST/PUT/DELETE - gérées par Background Sync
  if (event.request.method !== 'GET') {
    return;
  }
  
  event.respondWith(
    fetch(event.request)
      .then((response) => {
        // Mettre en cache les réponses réussies
        if (response.status === 200) {
          const responseClone = response.clone();
          caches.open(CACHE_NAME).then((cache) => {
            cache.put(event.request, responseClone);
          });
        }
        return response;
      })
      .catch(() => {
        // Fallback sur le cache si réseau indisponible
        return caches.match(event.request).then((cached) => {
          if (cached) {
            return cached;
          }
          // Page offline générique si rien en cache
          if (event.request.mode === 'navigate') {
            return caches.match('/app/express');
          }
        });
      })
  );
});

// Background Sync - synchronisation différée des opérations
self.addEventListener('sync', (event) => {
  if (event.tag === 'sync-patients') {
    event.waitUntil(syncPendingPatients());
  } else if (event.tag === 'sync-samples') {
    event.waitUntil(syncPendingSamples());
  } else if (event.tag === 'sync-results') {
    event.waitUntil(syncPendingResults());
  }
});

// Push Notifications - alertes temps réel
self.addEventListener('push', (event) => {
  const data = event.data.json();
  
  const options = {
    body: data.message,
    icon: '/static/icons/icon-192x192.png',
    badge: '/static/icons/badge-72x72.png',
    tag: data.tag || 'ruggylab-alert',
    requireInteraction: data.critical || false,
    actions: data.actions || [],
    data: data.payload || {}
  };
  
  event.waitUntil(
    self.registration.showNotification('RuggyLab Alert', options)
  );
});

// Notification click handler
self.addEventListener('notificationclick', (event) => {
  event.notification.close();
  
  const data = event.notification.data;
  
  event.waitUntil(
    clients.matchAll({ type: 'window' }).then((clientList) => {
      if (clientList.length > 0) {
        const client = clientList[0];
        client.focus();
        // Envoyer message à l'app pour navigation
        client.postMessage({
          type: 'notification-click',
          data: data
        });
      } else {
        clients.openWindow('/app/express');
      }
    })
  );
});

// Fonctions de synchronisation
async function syncPendingPatients() {
  const db = await openDB('ruggylab-offline', 1);
  const pending = await db.getAll('patients-pending');
  
  for (const patient of pending) {
    try {
      const response = await fetch('/api/v1/patients', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify(patient.data)
      });
      
      if (response.ok) {
        await db.delete('patients-pending', patient.id);
        // Notifier l'app de la réussite
        notifyClients('sync-success', { type: 'patient', id: patient.id });
      }
    } catch (error) {
      console.error('Sync patient failed:', error);
    }
  }
}

async function syncPendingSamples() {
  const db = await openDB('ruggylab-offline', 1);
  const pending = await db.getAll('samples-pending');
  
  for (const sample of pending) {
    try {
      const response = await fetch('/api/v1/samples', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify(sample.data)
      });
      
      if (response.ok) {
        await db.delete('samples-pending', sample.id);
        notifyClients('sync-success', { type: 'sample', id: sample.id });
      }
    } catch (error) {
      console.error('Sync sample failed:', error);
    }
  }
}

async function syncPendingResults() {
  const db = await openDB('ruggylab-offline', 1);
  const pending = await db.getAll('results-pending');
  
  for (const result of pending) {
    try {
      const response = await fetch('/api/v1/results', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify(result.data)
      });
      
      if (response.ok) {
        await db.delete('results-pending', result.id);
        notifyClients('sync-success', { type: 'result', id: result.id });
      }
    } catch (error) {
      console.error('Sync result failed:', error);
    }
  }
}

// Helper pour notifier les clients
function notifyClients(type, data) {
  clients.matchAll({ type: 'window' }).then((clientList) => {
    clientList.forEach((client) => {
      client.postMessage({ type, data });
    });
  });
}

// IndexedDB helper simplifié
function openDB(name, version) {
  return new Promise((resolve, reject) => {
    const request = indexedDB.open(name, version);
    request.onerror = () => reject(request.error);
    request.onsuccess = () => resolve(request.result);
    request.onupgradeneeded = (event) => {
      const db = event.target.result;
      if (!db.objectStoreNames.contains('patients-pending')) {
        db.createObjectStore('patients-pending', { keyPath: 'id' });
      }
      if (!db.objectStoreNames.contains('samples-pending')) {
        db.createObjectStore('samples-pending', { keyPath: 'id' });
      }
      if (!db.objectStoreNames.contains('results-pending')) {
        db.createObjectStore('results-pending', { keyPath: 'id' });
      }
    };
  });
}
