// RuggyLab OS — cockpit application script.
// Extrait de cockpit.html pour mise en cache navigateur (perf single-page).
// Référencé par <script src="/static/js/cockpit.js?v=..."> ; bumper ?v= à chaque modif.
    const $ = (id) => document.getElementById(id);
    const storage = {
      getItem: (key) => {
        try {
          return localStorage.getItem(key);
        } catch {
          return null;
        }
      },
      setItem: (key, value) => {
        try {
          localStorage.setItem(key, value);
        } catch {
          /* Storage blocked by browser settings */
        }
      },
      removeItem: (key) => {
        try {
          localStorage.removeItem(key);
        } catch {
          /* Storage blocked by browser settings */
        }
      }
    };
    let token = "";
    let currentView = "dashboard";
    let _currentRole = null;
    // Perf single-page : éviter de re-télécharger une vue déjà chargée
    // récemment lors d'une simple navigation. Les mutations rafraîchissent via
    // leurs loaders dédiés (loadSamples/loadResults…) et le bouton ↻ force.
    const _viewLoadedAt = {};
    const _VIEW_TTL_MS = 30000;
    let lastCreatedPatient = null;
    const API_PREFIX = "/api/v1";
    
    // Error handling and logging
    const errorHandler = {
      handle: (error, context = '') => {
        console.error(`Error in ${context}:`, error);
        log(`Erreur: ${error.message || error}`);
        showToast(`Une erreur est survenue: ${error.message || 'Erreur inconnue'}`, 'error');
      },
      
      async safeExecute(fn, context = '') {
        try {
          return await fn();
        } catch (error) {
          this.handle(error, context);
          throw error;
        }
      }
    };
    
    // Performance monitoring
    const perfMonitor = {
      measure: (name, fn) => {
        const start = performance.now();
        const result = fn();
        const end = performance.now();
        console.log(`${name} took ${end - start}ms`);
        return result;
      },
      
      async measureAsync(name, fn) {
        const start = performance.now();
        const result = await fn();
        const end = performance.now();
        console.log(`${name} took ${end - start}ms`);
        return result;
      }
    };
    
    // Debounce utility
    const debounce = (func, wait) => {
      let timeout;
      return function executedFunction(...args) {
        const later = () => {
          clearTimeout(timeout);
          func(...args);
        };
        clearTimeout(timeout);
        timeout = setTimeout(later, wait);
      };
    };
    
    // Input validation utilities
    const validator = {
      required: (value) => value && value.trim() !== '',
      numeric: (value) => !isNaN(Number(value)) && value !== '',
      date: (value) => !isNaN(Date.parse(value)),
      barcode: (value) => /^[A-Z0-9-]+$/.test(value),
      
      validateField: (field, rules) => {
        const value = field.value;
        const errors = [];
        
        if (rules.required && !validator.required(value)) {
          errors.push('Ce champ est requis');
        }
        
        if (rules.numeric && value && !validator.numeric(value)) {
          errors.push('Valeur numérique invalide');
        }
        
        if (rules.date && value && !validator.date(value)) {
          errors.push('Date invalide');
        }
        
        if (rules.barcode && value && !validator.barcode(value)) {
          errors.push('Code-barres invalide');
        }
        
        return errors;
      },
      
      showFieldErrors: (field, errors) => {
        field.classList.toggle('error-input', errors.length > 0);
        field.classList.toggle('success-input', errors.length === 0 && field.value);
        
        let errorDiv = field.parentNode.querySelector('.error-message');
        if (errors.length > 0) {
          if (!errorDiv) {
            errorDiv = document.createElement('div');
            errorDiv.className = 'error-message';
            field.parentNode.appendChild(errorDiv);
          }
          errorDiv.textContent = errors[0];
        } else if (errorDiv) {
          errorDiv.remove();
        }
      }
    };
    
    // Security utilities
    const security = {
      sanitize: (str) => {
        if (!str) return '';
        return str
          .replace(/[<>]/g, '')
          .replace(/[\x00-\x1F\x7F]/g, '')
          .trim();
      },
      
      sanitizeNumber: (str) => {
        const sanitized = str.replace(/[^0-9.-]/g, '');
        return sanitized === '' ? '' : sanitized;
      },
      
      escapeHtml: (str) => {
        if (!str) return '';
        const div = document.createElement('div');
        div.textContent = str;
        return div.innerHTML;
      },
      
      validateToken: () => {
        if (!token || token.length < 10) {
          logout();
          return false;
        }
        return true;
      },
      
      rateLimit: (() => {
        const lastCalls = {};
        return (key, limitMs = 1000) => {
          const now = Date.now();
          if (lastCalls[key] && now - lastCalls[key] < limitMs) {
            return false;
          }
          lastCalls[key] = now;
          return true;
        };
      })()
    };
    
    const savedTheme = storage.getItem("theme") || "light";
    function toggleTheme() {
      const current = document.documentElement.getAttribute("data-theme");
      const next = current === "dark" ? "light" : "dark";
      document.documentElement.setAttribute("data-theme", next);
      storage.setItem("theme", next);
      const btn = document.querySelector(".theme-toggle");
      if (btn) btn.textContent = next === "dark" ? "🌙" : "☀️";
    }
    
    // Enhanced loading states and user feedback
    const loadingStates = {
      showSkeleton: (element, count = 3) => {
        const skeletonHtml = Array(count).fill(0).map(() => 
          '<div class="skeleton" style="height: 20px; margin: 8px 0; border-radius: 4px;"></div>'
        ).join('');
        
        if (element.tagName === 'TBODY') {
          element.innerHTML = skeletonHtml.split('</div>').map(s => 
            `<tr><td colspan="100">${s}</div></td></tr>`
          ).join('');
        } else {
          element.innerHTML = skeletonHtml;
        }
      },
      
      hideSkeleton: (element, content) => {
        if (content) {
          element.innerHTML = content;
        } else {
          element.innerHTML = '';
        }
      },
      
      showLoadingOverlay: (message = 'Chargement...') => {
        const overlay = document.createElement('div');
        overlay.id = 'loadingOverlay';
        overlay.className = 'loading-overlay';
        overlay.innerHTML = `
          <div class="loading-content">
            <div class="spinner"></div>
            <div class="loading-text">${message}</div>
          </div>
        `;
        overlay.style.cssText = `
          position: fixed;
          top: 0;
          left: 0;
          right: 0;
          bottom: 0;
          background: rgba(0, 0, 0, 0.5);
          display: flex;
          align-items: center;
          justify-content: center;
          z-index: 9999;
        `;
        
        const style = document.createElement('style');
        style.textContent = `
          .loading-content {
            background: var(--panel);
            padding: 20px;
            border-radius: 8px;
            text-align: center;
            box-shadow: var(--shadow);
          }
          .spinner {
            width: 32px;
            height: 32px;
            border: 3px solid var(--line);
            border-top-color: var(--blue);
            border-radius: 50%;
            animation: spin 1s linear infinite;
            margin: 0 auto 12px;
          }
          .loading-text {
            color: var(--ink);
            font-size: 14px;
          }
        `;
        
        document.head.appendChild(style);
        document.body.appendChild(overlay);
      },
      
      hideLoadingOverlay: () => {
        const overlay = document.getElementById('loadingOverlay');
        if (overlay) overlay.remove();
      }
    };
    
    // Toast notifications
    function showToast(message, type = "success", duration = 4000) {
      const container = $("toastContainer");
      const toast = document.createElement("div");
      toast.className = `toast ${type}`;
      const icon = type === "success" ? "✓" : type === "error" ? "✗" : "⚠";
      const iconEl = document.createElement("span");
      iconEl.style.fontSize = "18px";
      iconEl.textContent = icon;
      const messageEl = document.createElement("span");
      messageEl.textContent = message;
      toast.append(iconEl, messageEl);
      container.appendChild(toast);
      setTimeout(() => {
        toast.style.animation = "slideIn 0.3s ease reverse";
        setTimeout(() => toast.remove(), 300);
      }, duration);
    }
    
    // Keyboard shortcuts and accessibility improvements
    const keyboard = {
      browserReservedCtrlKeys: new Set(['l', 'r', 's', 't', 'n', 'w', 'p', 'o', 'f', 'd']),
      shortcuts: {
        'Ctrl+Alt+K': () => {
          const query = $("patientQuery");
          if (query) {
            query.focus();
            showView('patients');
          }
        },
        'Ctrl+Alt+N': () => {
          showView('patients');
          setTimeout(() => $("patientIpp")?.focus(), 100);
        },
        'Ctrl+Alt+S': () => {
          showView('samples');
          setTimeout(() => $("sampleBarcode")?.focus(), 100);
        },
        'Ctrl+Alt+R': () => refreshCurrent(true),
        'Ctrl+Alt+D': () => showView('dashboard'),
        'Ctrl+Alt+Q': () => logout(),
        'Ctrl+Alt+T': () => toggleTheme(),
        'Escape': () => {
          document.querySelector('.side.open')?.classList.remove('open');
          document.querySelector('.sidebar-overlay.show')?.classList.remove('show');
        },
        'F1': (e) => {
          e.preventDefault();
          keyboard.showHelp();
        }
      },
      
      init: () => {
        document.addEventListener('keydown', (e) => {
          // Skip if user is typing in input fields
          if (e.target.tagName === 'INPUT' || e.target.tagName === 'TEXTAREA') {
            if (e.key === 'Escape') {
              e.target.blur();
            }
            return;
          }

          const browserKey = String(e.key || '').toLowerCase();
          if ((e.ctrlKey || e.metaKey) && !e.altKey && keyboard.browserReservedCtrlKeys.has(browserKey)) {
            return;
          }
          
          const key = [];
          if (e.ctrlKey) key.push('Ctrl');
          if (e.altKey) key.push('Alt');
          if (e.shiftKey) key.push('Shift');
          key.push(e.key.length === 1 ? e.key.toUpperCase() : e.key);
          
          const shortcut = key.join('+');
          if (keyboard.shortcuts[shortcut]) {
            e.preventDefault();
            keyboard.shortcuts[shortcut](e);
          }
        });
        
        // Add help button to topbar
        const helpBtn = document.createElement('button');
        helpBtn.className = 'ghost tooltip';
        helpBtn.setAttribute('data-tooltip', 'Raccourcis clavier (F1)');
        helpBtn.innerHTML = '?';
        helpBtn.onclick = () => keyboard.showHelp();
        helpBtn.style.cssText = 'width: 32px; height: 32px; padding: 0; font-weight: bold;';
        
        const actions = document.querySelector('.topbar .actions');
        if (actions) {
          actions.insertBefore(helpBtn, actions.firstChild);
        }
      },
      
      showHelp: () => {
        const modal = document.createElement('div');
        modal.className = 'modal-overlay';
        modal.style.cssText = `
          position: fixed;
          top: 0;
          left: 0;
          right: 0;
          bottom: 0;
          background: rgba(0, 0, 0, 0.5);
          display: flex;
          align-items: center;
          justify-content: center;
          z-index: 10000;
        `;
        
        const content = document.createElement('div');
        content.className = 'panel';
        content.style.cssText = 'max-width: 500px; width: 90%; max-height: 80vh; overflow-y: auto;';
        
        content.innerHTML = `
          <h3>Raccourcis clavier</h3>
          <div style="display: grid; gap: 8px; margin: 16px 0;">
            <div><kbd>Ctrl+Alt+K</kbd> - Recherche patients</div>
            <div><kbd>Ctrl+Alt+N</kbd> - Nouveau patient</div>
            <div><kbd>Ctrl+Alt+S</kbd> - Nouvel échantillon</div>
            <div><kbd>Ctrl+Alt+R</kbd> - Rafraîchir</div>
            <div><kbd>Ctrl+Alt+D</kbd> - Tableau de bord</div>
            <div><kbd>Ctrl+Alt+Q</kbd> - Déconnexion</div>
            <div><kbd>Ctrl+Alt+T</kbd> - Changer thème</div>
            <div><kbd>Échap</kbd> - Fermer menu/fenêtre</div>
            <div><kbd>F1</kbd> - Aide</div>
          </div>
          <div style="display: flex; gap: 8px; justify-content: flex-end;">
            <button onclick="this.closest('.modal-overlay').remove()">Fermer</button>
          </div>
        `;
        
        modal.appendChild(content);
        modal.onclick = (e) => {
          if (e.target === modal) modal.remove();
        };
        
        document.body.appendChild(modal);
        
        // Add keyboard styles
        if (!document.getElementById('keyboard-styles')) {
          const style = document.createElement('style');
          style.id = 'keyboard-styles';
          style.textContent = `
            kbd {
              background: var(--band);
              border: 1px solid var(--line);
              border-radius: 4px;
              padding: 2px 6px;
              font-family: monospace;
              font-size: 12px;
            }
          `;
          document.head.appendChild(style);
        }
      }
    };
    function toggleSidebar() {
      document.querySelector(".side").classList.toggle("open");
      document.querySelector(".sidebar-overlay")?.classList.toggle("show");
    }
    function closeSidebar() {
      document.querySelector(".side.open")?.classList.remove("open");
      document.querySelector(".sidebar-overlay.show")?.classList.remove("show");
      if (window.scrollX !== 0) window.scrollTo(0, window.scrollY);
    }
    
    // Button loading state
    function setLoading(btn, loading) {
      btn.classList.toggle("loading", loading);
      btn.disabled = loading;
    }
    const tubeGuides = {
      nfs: { code: "NFS", tube: "Tube EDTA violet", order: "Ordre 3", note: "Inversions douces 8 a 10 fois. Automate Dymind DH36." },
      poct: { code: "POCT", tube: "Tube heparine vert ou sang capillaire", order: "Ordre 4", note: "Acheminer rapidement pour Precis Expert." },
      malaria: { code: "PALU", tube: "Tube EDTA violet ou lame goutte epaisse", order: "Ordre 3", note: "Preparer lame, frottis mince et goutte epaisse; compatible IA offline." },
      urine: { code: "URIN", tube: "Flacon urine sterile", order: "Prelevement separe", note: "Identifier le flacon et tester rapidement." },
      coag: { code: "COAG", tube: "Tube citrate bleu", order: "Ordre 1", note: "Remplissage exact jusqu'au trait; inversions douces." }
    };
    const resultTemplates = {
      dh36: [
        ["WBC", "GB", "6.1"], ["RBC", "GR", "4.7"], ["HGB", "Hb g/L", "132"], ["HCT", "Ht %", "40"],
        ["MCV", "VGM fL", "86"], ["MCH", "TCMH pg", "29"], ["MCHC", "CCMH g/L", "330"], ["PLT", "Plaquettes", "250"]
      ],
      precis: [
        ["GLU", "Glucose", "0.45"], ["CHOL", "Cholesterol", "1.8"], ["UA", "Acide urique", "50"],
        ["LAC", "Lactate", "1.2"], ["KET", "Cetones", "0.2"]
      ],
      urine: [
        ["LEU", "Leucocytes", ""], ["NIT", "Nitrites", ""], ["PRO", "Proteines", ""],
        ["GLU", "Glucose", ""], ["KET", "Cetones", ""], ["BLD", "Sang", ""], ["PH", "pH", "6"]
      ],
      manual: [["VALUE", "Valeur", ""]]
    };

    function headers(json = true) {
      const h = { Authorization: `Bearer ${token}` };
      if (json) h["Content-Type"] = "application/json";
      return h;
    }
    function log(value) { $("log").textContent = typeof value === "string" ? value : JSON.stringify(value, null, 2); }
    function normalizeApiPath(path) {
      if (path.startsWith("http") || path.startsWith(API_PREFIX)) return path;
      return `${API_PREFIX}${path.startsWith("/") ? path : `/${path}`}`;
    }
    async function api(path, options = {}) {
      if (!security.validateToken() && !path.includes('/login/access-token')) {
        throw new Error('Session expirée');
      }
      
      // Rate limiting for non-GET requests
      if (options.method && options.method !== 'GET') {
        const key = `${path}_${options.method || 'GET'}`;
        if (!security.rateLimit(key, 500)) {
          throw new Error('Trop de requêtes, veuillez patienter');
        }
      }
      
      const response = await fetch(normalizeApiPath(path), options);
      const text = await response.text();
      let payload = text;
      try { payload = JSON.parse(text); } catch {}
      if (!response.ok) { 
        log(payload); 
        throw new Error(response.statusText); 
      }
      return payload;
    }
    function row(html) { const tr = document.createElement("tr"); tr.innerHTML = html; return tr; }
    function setRows(tableId, rows) {
      const table = $(tableId);
      const body = table?.querySelector("tbody");
      if (!body) return;
      body.innerHTML = "";
      if (rows.length === 0) {
        const colCount = table.querySelectorAll("thead th").length || 1;
        const tr = document.createElement("tr");
        tr.innerHTML = `<td colspan="${colCount}"><div class="empty-state">Aucune donnée</div></td>`;
        body.appendChild(tr);
      } else {
        rows.forEach((r) => body.appendChild(r));
      }
    }
    function renderAgentPriorities({ epi, stock, qc, perf, expiry, compliance, pendingCriticals }) {
      const container = $("agentPriorities");
      if (!container) return;

      const lowStockCount = stock?.low_stock_reagents?.length || 0;
      const rejectCount = qc?.reject_count || 0;
      const warnCount = qc?.warn_count || 0;
      const maintenanceCount = perf?.maintenance_due_count || 0;
      const expiryItems = Array.isArray(expiry) ? expiry : [];
      const expiredCount = expiryItems.filter((item) => item.is_expired).length;
      const expiryCount = expiryItems.length;
      const pendingCriticalCount = Array.isArray(pendingCriticals)
        ? pendingCriticals.length
        : compliance?.pending_criticals ?? epi?.critical_results ?? 0;

      const priorities = [
        {
          title: "Valeurs critiques",
          count: pendingCriticalCount,
          level: pendingCriticalCount > 0 ? "critical" : "ok",
          copy: pendingCriticalCount > 0
            ? "Résultats critiques à vérifier et prendre en charge sans délai."
            : "Aucune valeur critique en attente connue.",
          action: "Ouvrir résultats",
          view: "results",
        },
        {
          title: "Stocks bas",
          count: lowStockCount,
          level: lowStockCount > 0 ? "warning" : "ok",
          copy: lowStockCount > 0
            ? "Réactifs sous seuil: préparer le réapprovisionnement."
            : "Aucun réactif sous seuil d'alerte.",
          action: "Voir stocks",
          view: "stocks",
        },
        {
          title: "QC analytique",
          count: rejectCount || warnCount,
          level: rejectCount > 0 ? "critical" : warnCount > 0 ? "warning" : "ok",
          copy: rejectCount > 0
            ? "Contrôle en rejet: bloquer la validation concernée."
            : warnCount > 0
              ? "Contrôle en alerte: surveiller la série en cours."
              : "Contrôles chargés sans rejet actif.",
          action: "Ouvrir QC",
          view: "qc",
        },
        {
          title: "Maintenance",
          count: maintenanceCount,
          level: maintenanceCount > 0 ? "warning" : "ok",
          copy: maintenanceCount > 0
            ? "Échéances proches: planifier l'intervention équipement."
            : "Aucune maintenance due sous 7 jours.",
          action: "Équipements",
          view: "equipments",
        },
        {
          title: "Péremptions",
          count: expiryCount,
          level: expiredCount > 0 ? "critical" : expiryCount > 0 ? "warning" : "ok",
          copy: expiredCount > 0
            ? "Lot expiré détecté: retirer du circuit."
            : expiryCount > 0
              ? "Lots à contrôler avant utilisation."
              : "Aucune péremption proche signalée.",
          action: "Voir réactifs",
          view: "stocks",
        },
      ];

      container.innerHTML = priorities.map((item) => `
        <div class="priority-card ${item.level}">
          <div class="priority-title">
            <span>${security.escapeHtml(item.title)}</span>
            <span class="priority-count">${security.escapeHtml(String(item.count))}</span>
          </div>
          <div class="priority-copy">${security.escapeHtml(item.copy)}</div>
          <button class="ghost priority-action" onclick="showView('${item.view}')">${security.escapeHtml(item.action)}</button>
        </div>
      `).join("");
    }
    function stamp() {
      const d = new Date();
      return `${d.getFullYear()}${String(d.getMonth() + 1).padStart(2, "0")}${String(d.getDate()).padStart(2, "0")}${String(d.getHours()).padStart(2, "0")}${String(d.getMinutes()).padStart(2, "0")}${String(d.getSeconds()).padStart(2, "0")}`;
    }
    function updateTubeGuide() {
      const guide = tubeGuides[$("sampleExam").value];
      $("tubeGuide").innerHTML = `<div class="tube">${guide.tube}</div><div class="order">${guide.order}</div><div>${guide.note}</div>`;
    }
    function generateBarcode() {
      const patientId = $("samplePatientId").value || "0";
      const guide = tubeGuides[$("sampleExam").value];
      $("sampleBarcode").value = `${guide.code}-P${patientId}-${stamp()}`;
      updateTubeGuide();
    }
    function renderResultTemplate() {
      const fields = resultTemplates[$("resultTemplate").value] || resultTemplates.manual;
      const container = $("dataPoints") || $("resultFields");
      if (!container) return;
      container.innerHTML = fields.map(([key, label, value]) => `
        <div>
          <label>${label}</label>
          <input data-result-key="${key}" value="${value}" />
        </div>
      `).join("");
    }

    async function login() {
      return errorHandler.safeExecute(async () => {
        const usernameField = $("username");
        const passwordField = $("password");
        
        // Validate inputs
        const usernameErrors = validator.validateField(usernameField, { required: true });
        const passwordErrors = validator.validateField(passwordField, { required: true });
        
        validator.showFieldErrors(usernameField, usernameErrors);
        validator.showFieldErrors(passwordField, passwordErrors);
        
        if (usernameErrors.length > 0 || passwordErrors.length > 0) {
          throw new Error('Veuillez remplir tous les champs requis');
        }
        
        $("loginError").textContent = "";
        const form = new URLSearchParams();
        form.set("username", usernameField.value);
        form.set("password", passwordField.value);
        
        const payload = await perfMonitor.measureAsync('login', () => 
          api("/api/v1/login/access-token", { 
            method: "POST", 
            headers: { "Content-Type": "application/x-www-form-urlencoded" }, 
            body: form 
          })
        );
        
        token = payload.access_token;
        storage.setItem("ruggylab_token", token);
        await boot();
      }, 'login');
    }
    async function logout() {
      disconnectNotifications();
      // Révocation serveur du jeton d'accès (denylist) — best-effort.
      try {
        if (token) {
          await fetch(normalizeApiPath("/api/v1/login/logout"), {
            method: "POST",
            headers: { "Content-Type": "application/json", Authorization: `Bearer ${token}` },
            body: JSON.stringify({}),
          });
        }
      } catch {}
      storage.removeItem("ruggylab_token");
      token = "";
      $("appView").classList.add("hidden");
      $("loginView").classList.remove("hidden");
    }
    async function boot() {
      if (!token) return;
      try {
        const me = await api("/api/v1/users/me", { headers: headers(false) });
        $("userStatus").textContent = `${me.full_name || me.username} - ${me.role}`;
        $("loginView").classList.add("hidden");
        $("appView").classList.remove("hidden");
        closeSidebar();
        // Sidebar user footer
        const initials = (me.full_name || me.username || '?')
          .split(' ').map(w => w[0]).join('').slice(0, 2).toUpperCase();
        const sf = $('sideFooter'); if (sf) sf.style.display = 'flex';
        const sa = $('sideAvatar'); if (sa) sa.textContent = initials;
        const sn = $('sideUserName'); if (sn) sn.textContent = me.full_name || me.username;
        const sr = $('sideUserRole'); if (sr) sr.textContent = me.role || 'Utilisateur';
        applyRoleNavigation(me.role);
        startClock();
        connectNotifications();
        updateTubeGuide();
        renderResultTemplate();
        if ($('stockDrugLines') && $('stockDrugLines').children.length === 0) {
          addStockDrugLine({
            dci_code: 'ARTEMETHER-LUMEFANTRINE',
            current_stock: 80,
            cmm_units: 120,
            disease_category: 'ANTIMALARIAL',
            unit_cost_xof: 250
          });
        }
        await loadDashboard();
        _navFromHash();  // rechargement sur #/results → restaure la vue (lien profond)
      } catch { logout(); }
    }
    function showView(name) {
      const view = $(name);
      const navButton = document.querySelector(`.nav button[data-view="${name}"]`);
      if (!view || !navButton) {
        showToast(`Vue indisponible: ${name}`, "error");
        return;
      }
      // Vue masquée pour le rôle courant (y compris URL forgée) → tableau de bord
      if ((ROLE_HIDDEN_VIEWS[_currentRole] || []).includes(name) && name !== "dashboard") {
        return showView("dashboard");
      }
      currentView = name;
      document.querySelectorAll(".view").forEach((el) => el.classList.add("hidden"));
      view.classList.remove("hidden");
      document.querySelectorAll(".nav button").forEach((b) => b.classList.toggle("active", b.dataset.view === name));
      $("viewTitle").textContent = navButton.textContent;
      // Synchronise l'URL : lien partageable, bouton Précédent, rechargement sans perte de vue
      const target = "#/" + name;
      if (location.hash !== target) location.hash = target;
      closeSidebar();
      refreshCurrent();
    }
    // Routage par hash : restaure/navigue la vue depuis l'URL (#/results, #/patients…)
    function _navFromHash() {
      const name = (location.hash || "").replace(/^#\/?/, "").trim() || "dashboard";
      if (name === currentView) return;
      if ($(name) && document.querySelector(`.nav button[data-view="${name}"]`)) {
        showView(name);
      } else {
        showView("dashboard");
      }
    }
    window.addEventListener("hashchange", _navFromHash);
    async function refreshCurrent(force = false) {
      // Navigation : si la vue a été chargée il y a moins de _VIEW_TTL_MS, on
      // saute le re-téléchargement (navigation instantanée). Le bouton ↻, le
      // raccourci, la reconnexion et la fin de synchro passent force=true.
      const now = Date.now();
      if (!force && _viewLoadedAt[currentView] && now - _viewLoadedAt[currentView] < _VIEW_TTL_MS) {
        return;
      }
      _viewLoadedAt[currentView] = now;
      if (currentView === "dashboard" || currentView === "reports") await loadDashboard();
      if (currentView === "worklist") await loadWorklist();
      if (currentView === "reports") await loadCriticalCompliance();
      if (currentView === "patients") await loadPatients();

      if (currentView === "results") {
        await Promise.all([loadResults(), loadCriticalRanges(), loadDeltaRules(), loadRefRanges(), loadNotifConfigs(), loadPendingCriticals(), loadAutoValidationConfigs(), loadBioref(), loadCodeMappings(), loadResultEquipmentOptions()]);
      }
      if (currentView === "stocks") { await loadReagents(); await loadExpiryAlerts(); }
      if (currentView === "epidemio") await loadEpidemio();
      if (currentView === "users") await loadUsers();
      if (currentView === "samples") { await loadSamples(); setTimeout(() => $('barcodeScanner')?.focus(), 150); }
      if (currentView === "equipments") await Promise.all([loadEquipments(), loadMaintenances()]);
      if (currentView === "audit") await loadAudit();
      if (currentView === "qc") await loadQc();
      if (currentView === "stats") await loadStats();
      if (currentView === "quality") await loadQuality();
      if (currentView === "tat") await loadTat();
      if (currentView === "prescription") await loadExamOrdersView();
      if (currentView === "invoices") await Promise.all([loadFinanceSummary(), loadInvoices(), ensureInvoiceLine()]);
    }
    function _worklistBadge(priority) {
      const labels = { critical: "Critique", overdue: "Hors délai", urgent: "Urgent", blocked: "Bloqué", normal: "Routine" };
      const cls = priority === "critical" ? "bad" : priority === "overdue" || priority === "urgent" ? "" : priority === "blocked" ? "bad" : "ok";
      const style = priority === "overdue" || priority === "urgent" ? ' style="background:var(--amber);color:#fff;"' : "";
      return `<span class="pill ${cls}"${style}>${labels[priority] || priority}</span>`;
    }
    function _worklistActionButton(action, itemId) {
      if (!action) return "";
      const label = security.escapeHtml(action.label || "Ouvrir");
      const encoded = encodeURIComponent(JSON.stringify(action));
      if ((action.path || "").startsWith("#")) {
        return `<button class="ghost" onclick="openWorklistLink('${encodeURIComponent(action.path)}')">${label}</button>`;
      }
      return `<button class="${action.style === "danger" ? "danger" : "ghost"}" onclick="runWorklistAction('${encoded}', '${security.escapeHtml(itemId)}')">${label}</button>`;
    }
    async function openWorklistLink(encodedPath) {
      const path = decodeURIComponent(encodedPath || "%23/dashboard");
      const [, query = ""] = path.split("?");
      const params = new URLSearchParams(query);
      const name = path.replace(/^#\/?/, "").split(/[?#]/)[0] || "dashboard";
      if ($(name) && document.querySelector(`.nav button[data-view="${name}"]`)) {
        showView(name);
      } else {
        showView("dashboard");
        return;
      }
      const resultId = Number(params.get("result"));
      const sampleId = Number(params.get("sample"));
      const controlId = Number(params.get("control"));
      const ncId = Number(params.get("nc"));
      if (name === "results" && resultId) await openResultDetail(resultId);
      if (name === "samples" && sampleId) await openSampleFromWorklist(sampleId);
      if (name === "qc" && controlId) await openQcControlFromWorklist(controlId);
      if (name === "quality" && ncId) await openNcDetail(ncId);
    }
    async function openSampleFromWorklist(sampleId) {
      await loadSamples();
      const tr = document.querySelector(`#samplesTable tbody tr[data-sample-id="${sampleId}"]`);
      if (!tr) {
        showToast("Échantillon introuvable dans la liste", "error");
        return;
      }
      tr.style.outline = "3px solid var(--blue)";
      tr.style.outlineOffset = "-3px";
      tr.scrollIntoView({ behavior: "smooth", block: "center" });
    }
    async function openQcControlFromWorklist(controlId) {
      const controls = await api("/api/v1/qc/controls", { headers: headers(false) });
      const control = (controls || []).find((item) => Number(item.id) === Number(controlId));
      if (!control) {
        showToast("Contrôle QC introuvable", "error");
        return;
      }
      await selectQcControl(control);
    }
    async function runWorklistAction(encodedAction, itemId) {
      const action = JSON.parse(decodeURIComponent(encodedAction));
      const label = action.label || "cette action";
      if (!confirm(`${label} ? Cette action sera tracée si elle modifie un dossier.`)) return;
      const options = { method: action.method || "GET", headers: headers(false) };
      await api(action.path, options);
      showToast(`Action effectuée: ${itemId}`, "success");
      await loadWorklist();
      await loadDashboard();
    }
    async function loadWorklist(btn = null) {
      if (btn) setLoading(btn, true);
      try {
        const category = $("worklistCategory")?.value || "";
        const query = category ? `?category=${encodeURIComponent(category)}` : "";
        const payload = await api(`/api/v1/worklist/my${query}`, { headers: headers(false) });
        $("wlTotal").textContent = payload.summary.total;
        $("wlCritical").textContent = payload.summary.critical;
        $("wlOverdue").textContent = payload.summary.overdue;
        $("wlBlocked").textContent = payload.summary.blocked;
        setRows("worklistTable", (payload.items || []).map((item) => {
          const primaryAction = (item.actions || [])[0];
          const secondaryAction = (item.actions || [])[1];
          return row(
            `<td>${_worklistBadge(item.priority)}</td>` +
            `<td><strong>${security.escapeHtml(item.category)}</strong><br><small>${security.escapeHtml(item.unit || "")}</small></td>` +
            `<td><strong>${security.escapeHtml(item.title)}</strong><br><small>${security.escapeHtml(item.subtitle || "")}</small></td>` +
            `<td>${security.escapeHtml(item.status)}</td>` +
            `<td>${item.due_at ? new Date(item.due_at).toLocaleString("fr-FR") : "—"}</td>` +
            `<td>${_worklistActionButton(primaryAction, item.id)} ${_worklistActionButton(secondaryAction, item.id)}</td>`
          );
        }));
        if (!payload.items || payload.items.length === 0) {
          setRows("worklistTable", [row('<td colspan="6" style="text-align:center;color:var(--muted);">Aucune action prioritaire.</td>')]);
        }
      } finally {
        if (btn) setLoading(btn, false);
      }
    }
    async function loadDashboard(btn = null) {
      if (btn) setLoading(btn, true);
      try {
        const [epi, stock, qc, perf, expiry, compliance, pendingCriticals] = await Promise.all([
          api("/api/v1/reports/epidemiology-summary?days=30", { headers: headers(false) }),
          api("/api/v1/reports/stock-dashboard", { headers: headers(false) }),
          api("/api/v1/reports/qc-summary", { headers: headers(false) }),
          api("/api/v1/stats/summary?days=30", { headers: headers(false) }).catch(() => null),
          api("/api/v1/reagents/expiring?days=30", { headers: headers(false) }).catch(() => null),
          api("/api/v1/reports/compliance-summary?days=30", { headers: headers(false) }).catch(() => null),
          api("/api/v1/critical-alerts/pending", { headers: headers(false) }).catch(() => []),
        ]);
        const pendingCriticalCount = Array.isArray(pendingCriticals)
          ? pendingCriticals.length
          : compliance?.pending_criticals ?? epi.critical_results;
        renderAgentPriorities({ epi, stock, qc, perf, expiry, compliance, pendingCriticals });
        $("mResults").textContent = epi.total_results;
        $("mCritical").textContent = pendingCriticalCount;
        const mCriticalPanel = $("mCriticalPanel");
        if (mCriticalPanel) {
          mCriticalPanel.classList.remove("metric-rose", "metric-teal");
          mCriticalPanel.classList.add(pendingCriticalCount > 0 ? "metric-rose" : "metric-teal");
        }
        $("mMalaria").textContent = epi.malaria_positive;
        const lowStockCount = stock.low_stock_reagents.length;
        $("mLowStock").textContent = lowStockCount;
        const mLSP = $("mLowStockPanel");
        if (mLSP) {
          mLSP.classList.remove("metric-amber", "metric-teal");
          mLSP.classList.add(lowStockCount > 0 ? "metric-amber" : "metric-teal");
        }
        // QC metric panel
        const mQcEl = $("mQc");
        const mQcPanel = $("mQcPanel");
        if (mQcEl && mQcPanel) {
          const total = qc.controls.length;
          const rejects = qc.reject_count;
          const warns = qc.warn_count;
          mQcEl.textContent = total > 0 ? (rejects > 0 ? rejects + " ⛔" : warns > 0 ? warns + " ⚠" : total + " ✓") : "—";
          mQcPanel.classList.remove("metric-rose", "metric-amber", "metric-teal");
          mQcPanel.classList.add(rejects > 0 ? "metric-rose" : warns > 0 ? "metric-amber" : "metric-teal");
        }
        // QC reject/warn badges
        const rb = $("qcRejectBadge"); const wb = $("qcWarnBadge");
        if (rb) rb.style.display = qc.reject_count > 0 ? "" : "none";
        if (wb) wb.style.display = (qc.warn_count > 0 && qc.reject_count === 0) ? "" : "none";
        // QC summary table
        const _statusBadge = (s) => {
          if (s === "reject") return '<span class="pill bad">Rejet</span>';
          if (s === "warn")   return '<span class="pill" style="background:var(--amber);color:#fff;">Alerte 1-2s</span>';
          if (s === "ok")     return '<span class="pill ok">OK</span>';
          return '<span class="pill" style="background:var(--muted);color:#fff;">Aucune donnée</span>';
        };
        setRows("dashQcTable", qc.controls.map(c => {
          const tr = row(
            `<td><strong>${security.escapeHtml(c.analyte)}</strong></td>` +
            `<td>${security.escapeHtml(c.level)}</td>` +
            `<td style="font-variant-numeric:tabular-nums;">${c.last_value !== null ? c.last_value : '—'} <small style="color:var(--muted);">${security.escapeHtml(c.unit || '')}</small></td>` +
            `<td>${c.last_date || '—'}</td>` +
            `<td><small style="color:var(--rose);">${(c.violations || []).join(', ') || '—'}</small></td>` +
            `<td>${_statusBadge(c.status)}</td>`
          );
          if (c.status === "reject") tr.classList.add("row-critical");
          else if (c.status === "warn") tr.classList.add("row-warning");
          return tr;
        }));
        setRows("markerTable", epi.marker_breakdown.map((m) => row(`<td>${m.marker}</td><td>${m.low}</td><td>${m.normal}</td><td>${m.high}</td><td>${m.critical}</td>`)));
        setRows("lowStockTable", stock.low_stock_reagents.map(r => {
          const pct = r.alert_threshold > 0 ? Math.round((r.current_stock / r.alert_threshold) * 100) : 0;
          const barColor = r.current_stock === 0 ? '#be123c' : '#b45309';
          const tr = row(
            `<td><strong>${security.escapeHtml(r.name)}</strong></td>` +
            `<td style="font-variant-numeric:tabular-nums;">${r.current_stock} <small style="color:var(--muted);">${security.escapeHtml(r.unit || '')}</small></td>` +
            `<td>${r.alert_threshold}</td>` +
            `<td style="min-width:70px;">` +
              `<div style="background:#e5e7eb;border-radius:3px;height:6px;width:72px;overflow:hidden;" title="${pct}% du seuil">` +
                `<div style="width:${Math.min(pct,100)}%;height:100%;background:${barColor};transition:width .3s;"></div>` +
              `</div>` +
            `</td>` +
            `<td><button class="ghost" style="font-size:11px;padding:3px 8px;" onclick="showView('stocks')">↑ Réapprovisionner</button></td>`
          );
          if (r.current_stock === 0)                                   tr.classList.add('row-critical');
          else if (r.current_stock <= r.alert_threshold)              tr.classList.add('row-warning');
          return tr;
        }));
        // Maintenance due metric
        if (perf && $('mMnt')) {
          const mntCount = perf.maintenance_due_count || 0;
          $('mMnt').textContent = mntCount;
          const mMntP = $('mMntPanel');
          if (mMntP) {
            mMntP.classList.remove('metric-amber', 'metric-teal', 'metric-rose');
            mMntP.classList.add(mntCount > 0 ? 'metric-amber' : 'metric-teal');
          }
        }
        // Expiry metric
        if (expiry !== null && $('mExpiry')) {
          const expiryCount = Array.isArray(expiry) ? expiry.length : 0;
          $('mExpiry').textContent = expiryCount;
          const mExpiryP = $('mExpiryPanel');
          if (mExpiryP) {
            mExpiryP.classList.remove('metric-amber', 'metric-teal', 'metric-rose');
            const expiredCount = Array.isArray(expiry) ? expiry.filter(r => r.is_expired).length : 0;
            mExpiryP.classList.add(expiredCount > 0 ? 'metric-rose' : expiryCount > 0 ? 'metric-amber' : 'metric-teal');
          }
        }
        // Compliance metric (ISO 15189)
        if (compliance && $('mCompliance')) {
          $('mCompliance').textContent = (compliance.validation_rate_pct ?? 0) + '%';
          const mCompP = $('mCompliancePanel');
          if (mCompP) {
            mCompP.classList.remove('metric-amber', 'metric-teal', 'metric-rose');
            mCompP.classList.add(compliance.status === 'compliant' ? 'metric-teal' : 'metric-amber');
          }
          $('mCompliance').title = compliance.status === 'compliant'
            ? 'Conforme — validation ≥99 %, critiques acquittés'
            : `Attention — ${compliance.pending_criticals} critique(s) en attente`;
        }
        showToast("Tableau de bord actualisé", "success");
      } catch (e) {
        showToast("Erreur lors du chargement du dashboard", "error");
      } finally {
        if (btn) setLoading(btn, false);
      }
    }
    async function loadPatients() {
      const tbody = $("patientsTable").querySelector("tbody");
      loadingStates.showSkeleton(tbody, 5);
      
      try {
        const data = await api(`/api/v1/patients?q=${encodeURIComponent($("patientQuery").value || "")}`, { headers: headers(false) });
        const rows = data.items.map((p) => row(
          `<td>${p.id}</td>` +
          `<td><code>${security.escapeHtml(p.ipp_unique_id)}</code></td>` +
          `<td>${security.escapeHtml(p.first_name + ' ' + p.last_name)}</td>` +
          `<td>${p.sex || ''}</td>` +
          `<td style="white-space:nowrap;">` +
            `<button class="ghost" title="Dossier complet" onclick="openDossier(${p.id})">📂 Dossier</button> ` +
            `<button class="ghost" title="Imprimer étiquettes tubes" onclick='printPatientLabels(${JSON.stringify(p)})'>🏷️</button>` +
          `</td>`
        ));
        setRows("patientsTable", rows);
      } catch (error) {
        tbody.innerHTML = '<tr><td colspan="5" style="text-align: center; color: var(--rose);">Erreur de chargement</td></tr>';
        throw error;
      }
    }
    async function createPatient(btn) {
      return errorHandler.safeExecute(async () => {
        setLoading(btn, true);
        
        // Validate all fields
        const fields = {
          patientIpp: { required: true },
          patientFirst: { required: true },
          patientLast: { required: true },
          patientBirth: { required: true, date: true },
          patientRank: { required: false }
        };
        
        let hasErrors = false;
        Object.entries(fields).forEach(([fieldId, rules]) => {
          const field = $(fieldId);
          const errors = validator.validateField(field, rules);
          validator.showFieldErrors(field, errors);
          if (errors.length > 0) hasErrors = true;
        });
        
        if (hasErrors) {
          throw new Error('Veuillez corriger les erreurs dans le formulaire');
        }
        
        const body = { 
          ipp_unique_id: $("patientIpp").value, 
          first_name: $("patientFirst").value, 
          last_name: $("patientLast").value, 
          birth_date: $("patientBirth").value, 
          sex: $("patientSex").value,
          rank: $("patientRank").value || null,
          unit: ($("patientUnit")?.value || "").trim() || null
        };
        
        const created = await perfMonitor.measureAsync('createPatient', () =>
          api("/api/v1/patients", { method: "POST", headers: headers(), body: JSON.stringify(body) })
        );
        
        lastCreatedPatient = created;
        $("createdPatientId").textContent = `ID patient: ${created.id}`;
        $("createdPatientName").textContent = `${created.ipp_unique_id} - ${created.first_name} ${created.last_name}`;
        $("patientCreated").classList.remove("hidden");
        showToast(`Patient ${created.first_name} ${created.last_name} créé avec succès`, "success");
        
        // Clear form
        ["patientIpp", "patientFirst", "patientLast", "patientBirth", "patientRank", "patientUnit"].forEach(id => {
          const field = $(id);
          field.value = "";
          field.classList.remove('success-input', 'error-input');
          const errorDiv = field.parentNode.querySelector('.error-message');
          if (errorDiv) errorDiv.remove();
        });
        
        await loadPatients();
      }, 'createPatient').finally(() => setLoading(btn, false));
    }
    function useCreatedPatientForSample() {
      if (!lastCreatedPatient) return;
      const p = lastCreatedPatient;
      $("samplePatientId").value = p.id;
      const label = `${p.ipp_unique_id} — ${p.first_name} ${p.last_name}`;
      if ($("samplePatientSearch")) $("samplePatientSearch").value = label;
      if ($("samplePatientSelected")) $("samplePatientSelected").textContent = "✓ " + label;
      showView("samples");
      generateBarcode();
    }

    // ── Saisie « labo réel » : sélection patient par IPP/nom, échantillon par code-barres ──
    const ROLE_HIDDEN_VIEWS = {
      // Le technicien voit la prescription d'examens (suivi du fil) mais ce n'est
      // pas obligatoire ; la finance (factures, BNPL) lui est masquée.
      technician: ["users", "audit", "bnpl", "invoices", "pharmacy", "ai_training", "registre", "equipments"],
      // Finance déléguée au comptable : l'officier ne gère ni factures ni BNPL.
      officer: ["users", "audit", "ai_training", "bnpl", "invoices"],
      // Comptable : facturation + paiements + activité agrégée (dashboard, stats).
      // Aucun accès clinique (renforcé côté backend par forbid_accountant).
      accountant: ["patients", "samples", "results", "epidemio", "machines", "imaging", "reports", "qc", "tat", "pharmacy", "prescription", "stocks", "equipments", "ai_training", "registre", "quality", "users", "audit"],
      admin: [],
    };
    function applyRoleNavigation(role) {
      _currentRole = role;
      const hidden = ROLE_HIDDEN_VIEWS[role] || [];
      document.querySelectorAll('.nav button[data-view]').forEach((b) => {
        b.style.display = hidden.includes(b.dataset.view) ? "none" : "";
      });
      // Si la vue courante n'est plus autorisée, revenir au tableau de bord
      if (hidden.includes(currentView)) showView("dashboard");
    }

    let _samplePatientTimer = null;
    let _samplePatientResults = [];
    function searchSamplePatient(q) {
      clearTimeout(_samplePatientTimer);
      const box = $("samplePatientMatches");
      q = (q || "").trim();
      $("samplePatientId").value = "";  // toute frappe invalide la sélection précédente
      $("samplePatientSelected").textContent = "";
      if (q.length < 2) { box.style.display = "none"; return; }
      _samplePatientTimer = setTimeout(async () => {
        try {
          const data = await api(`/api/v1/patients?q=${encodeURIComponent(q)}&limit=8`, { headers: headers(false) });
          _samplePatientResults = data.items || [];
          if (!_samplePatientResults.length) {
            box.innerHTML = '<div class="picker-item" style="color:var(--muted);">Aucun patient</div>';
          } else {
            box.innerHTML = _samplePatientResults.map((p, i) =>
              `<div class="picker-item" onclick="pickSamplePatient(${i})">` +
              `<code>${security.escapeHtml(p.ipp_unique_id)}</code> — ${security.escapeHtml(p.first_name + " " + p.last_name)}</div>`
            ).join("");
          }
          box.style.display = "block";
        } catch { box.style.display = "none"; }
      }, 250);
    }
    function pickSamplePatient(idx) {
      const p = _samplePatientResults[idx];
      if (!p) return;
      const label = `${p.ipp_unique_id} — ${p.first_name} ${p.last_name}`;
      $("samplePatientId").value = p.id;
      $("samplePatientSearch").value = label;
      $("samplePatientSelected").textContent = "✓ " + label;
      $("samplePatientMatches").style.display = "none";
    }

    async function resolveResultSample(barcode) {
      if (!barcode) return;
      try {
        const s = await api(`/api/v1/samples/by-barcode/${encodeURIComponent(barcode)}`, { headers: headers(false) });
        $("resultSampleId").value = s.id;
        $("resultSampleSelected").textContent = `✓ Échantillon #${s.id} (${security.escapeHtml(barcode)})`;
      } catch {
        $("resultSampleId").value = "";
        $("resultSampleSelected").textContent = "✗ Code-barres introuvable";
        showToast("Code-barres échantillon introuvable", "error");
      }
    }

    async function loadResultEquipmentOptions() {
      const sel = $("resultEquipmentId");
      if (!sel) return;
      try {
        const data = await api("/api/v1/equipments", { headers: headers(false) });
        const items = _listItems(data);
        const current = sel.value;
        sel.innerHTML = '<option value="">— Manuel / non spécifié —</option>' +
          items.map((e) => `<option value="${e.id}">${security.escapeHtml(e.name)}</option>`).join("");
        if (current) sel.value = current;
      } catch { /* liste équipements indisponible : on garde l'option Manuel */ }
    }

    // ── Prescription d'examens : création + suivi du fil ──────────────────────
    let _examCatalogCache = [];
    let _rxPatientTimer = null;
    let _rxPatientResults = [];
    const _ORDER_STATUS_LABELS = { prescribed: "Prescrit", collected: "Prélevé", in_progress: "En cours", completed: "Terminé", cancelled: "Annulé" };

    async function loadExamOrdersView() {
      await Promise.all([loadExamCatalog(), loadExamOrders()]);
    }
    async function loadExamCatalog() {
      const box = $("rxExamChecklist");
      if (!box) return;
      try {
        if (_examCatalogCache.length === 0) {
          _examCatalogCache = _listItems(await api("/api/v1/tat/catalog", { headers: headers(false) }));
        }
        box.classList.remove("muted");
        box.innerHTML = _examCatalogCache.map((e) =>
          `<label class="exam-opt"><input type="checkbox" value="${security.escapeHtml(e.code)}" data-label="${security.escapeHtml(e.label || e.code)}"> ${security.escapeHtml(e.code)} — ${security.escapeHtml(e.label || "")}</label>`
        ).join("") || '<span class="muted">Catalogue vide.</span>';
      } catch { box.innerHTML = '<span class="muted">Catalogue indisponible.</span>'; }
    }
    function searchRxPatient(q) {
      clearTimeout(_rxPatientTimer);
      const box = $("rxPatientMatches");
      q = (q || "").trim();
      $("rxOrderPatientId").value = "";
      $("rxPatientSelected").textContent = "";
      if (q.length < 2) { box.style.display = "none"; return; }
      _rxPatientTimer = setTimeout(async () => {
        try {
          const data = await api(`/api/v1/patients?q=${encodeURIComponent(q)}&limit=8`, { headers: headers(false) });
          _rxPatientResults = _listItems(data);
          if (_rxPatientResults.length === 0) { box.style.display = "none"; return; }
          box.innerHTML = _rxPatientResults.map((p, i) =>
            `<div class="picker-item" onclick="pickRxPatient(${i})">${security.escapeHtml(p.ipp_unique_id || "")} — ${security.escapeHtml((p.last_name || "") + " " + (p.first_name || ""))}</div>`
          ).join("");
          box.style.display = "block";
        } catch { box.style.display = "none"; }
      }, 250);
    }
    function pickRxPatient(idx) {
      const p = _rxPatientResults[idx];
      if (!p) return;
      $("rxOrderPatientId").value = p.id;
      $("rxPatientSearch").value = `${p.ipp_unique_id} — ${p.last_name} ${p.first_name}`;
      $("rxPatientSelected").textContent = `Patient sélectionné : #${p.id}`;
      $("rxPatientMatches").style.display = "none";
    }
    async function createExamOrder(btn) {
      const pid = $("rxOrderPatientId").value;
      if (!pid) { showToast("Sélectionnez un patient.", "error"); return; }
      const exams = Array.from(document.querySelectorAll('#rxExamChecklist input[type=checkbox]:checked'))
        .map((c) => ({ exam_code: c.value, exam_label: c.dataset.label }));
      if (exams.length === 0) { showToast("Sélectionnez au moins un examen.", "error"); return; }
      setLoading(btn, true);
      try {
        await api("/api/v1/exam-orders", {
          method: "POST", headers: headers(),
          body: JSON.stringify({
            patient_id: Number(pid),
            prescriber: $("rxOrderPrescriber").value || null,
            clinical_info: $("rxOrderClinical").value || null,
            priority: $("rxOrderPriority").value,
            exams,
          }),
        });
        showToast("Prescription créée.", "success");
        document.querySelectorAll('#rxExamChecklist input:checked').forEach((c) => { c.checked = false; });
        $("rxPatientSearch").value = ""; $("rxOrderPatientId").value = ""; $("rxPatientSelected").textContent = "";
        await loadExamOrders();
      } catch { showToast("Échec de la création.", "error"); }
      finally { setLoading(btn, false); }
    }
    async function loadExamOrders() {
      const tbody = $("examOrdersTable").querySelector("tbody");
      try {
        const rows = _listItems(await api("/api/v1/exam-orders?limit=50", { headers: headers(false) }));
        if (rows.length === 0) { tbody.innerHTML = '<tr><td colspan="6" class="muted">Aucune prescription.</td></tr>'; return; }
        tbody.innerHTML = rows.map((o) => {
          const done = o.items.filter((i) => i.status === "resulted").length;
          const tot = o.items.filter((i) => i.status !== "cancelled").length;
          return `<tr><td>#${o.id}</td><td>${o.patient_id}</td><td>${security.escapeHtml(o.priority)}</td><td>${_ORDER_STATUS_LABELS[o.status] || o.status}</td><td>${done}/${tot}</td><td><button class="ghost" onclick="openOrderThread(${o.id})">Suivre le fil</button></td></tr>`;
        }).join("");
      } catch { tbody.innerHTML = '<tr><td colspan="6" class="muted">Indisponible.</td></tr>'; }
    }
    async function openOrderThread(orderId) {
      const panel = $("rxThreadPanel");
      panel.innerHTML = '<div class="muted">Chargement…</div>';
      try {
        const t = await api(`/api/v1/exam-orders/${orderId}/thread`, { headers: headers(false) });
        const steps = t.steps.map((s) => {
          const icon = s.status === "resulted" ? (s.is_critical ? "🔴" : "✅") : "⏳";
          return `<tr><td>${icon}</td><td>${security.escapeHtml(s.exam_code)}</td><td>${security.escapeHtml(s.exam_label || "")}</td><td>${s.status === "resulted" ? "Résultat #" + s.result_id : "En attente"}</td></tr>`;
        }).join("");
        const collect = t.sample_id
          ? `<div class="muted" style="margin:6px 0;">Échantillon : ${security.escapeHtml(t.sample_barcode || "")} (${security.escapeHtml(t.sample_status || "")})</div>`
          : `<div class="form" style="margin:6px 0;"><label>Rattacher l'échantillon prélevé (code-barres)</label><div class="toolbar"><input id="rxCollectBarcode" placeholder="Scanner / saisir"><button onclick="collectOrderSample(${orderId})">Rattacher</button></div></div>`;
        panel.innerHTML =
          `<div><strong>Prescription #${t.order_id}</strong> — ${_ORDER_STATUS_LABELS[t.status] || t.status} · ${t.progress_pct}%</div>` +
          `<div class="muted">${security.escapeHtml(t.patient_label || "")}${t.prescriber ? " · " + security.escapeHtml(t.prescriber) : ""}</div>` +
          collect +
          `<table style="margin-top:8px;"><thead><tr><th></th><th>Examen</th><th>Libellé</th><th>État</th></tr></thead><tbody>${steps}</tbody></table>` +
          `<div class="actions" style="margin-top:8px;"><button class="success" onclick="generateInvoiceFromOrder(${t.order_id})">💵 Générer la facture</button></div>`;
      } catch { panel.innerHTML = '<div class="muted">Fil indisponible.</div>'; }
    }
    async function generateInvoiceFromOrder(orderId) {
      try {
        const inv = await api(`/api/v1/exam-orders/${orderId}/invoice`, { method: "POST", headers: headers(), body: "{}" });
        showToast(`Facture ${inv.invoice_number} générée · reste patient ${Number(inv.patient_due_xof).toLocaleString("fr-FR")} FCFA.`, "success");
      } catch { showToast("Facturation impossible (déjà émise, ou tarifs à initialiser).", "error"); }
    }
    async function collectOrderSample(orderId) {
      const barcode = ($("rxCollectBarcode")?.value || "").trim();
      if (!barcode) { showToast("Saisir un code-barres.", "error"); return; }
      try {
        await api(`/api/v1/exam-orders/${orderId}/collect`, { method: "POST", headers: headers(), body: JSON.stringify({ barcode }) });
        showToast("Échantillon rattaché.", "success");
        await openOrderThread(orderId); await loadExamOrders();
      } catch { showToast("Code-barres introuvable.", "error"); }
    }

    // ── Comptabilité : facturation des examens, encaissements, créances ───────
    const _INV_STATUS_LABELS = { draft: "Brouillon", issued: "Émise", partially_paid: "Partiel", paid: "Payée", cancelled: "Annulée" };
    function toggleInvInsurance() {
      $("invInsuranceWrap").style.display = $("invPatientType").value === "INSURED" ? "" : "none";
    }
    function ensureInvoiceLine() { if ($("invLines") && $("invLines").children.length === 0) addInvoiceLine(); }
    function addInvoiceLine(code = "", label = "", price = "") {
      const wrap = $("invLines"); if (!wrap) return;
      const r = document.createElement("div");
      r.className = "inv-line grid3";
      r.innerHTML =
        `<input placeholder="Code examen" value="${security.escapeHtml(code)}" class="inv-code">` +
        `<input placeholder="Libellé" value="${security.escapeHtml(label)}" class="inv-label">` +
        `<div class="toolbar"><input type="number" min="0" placeholder="Prix XOF" value="${price}" class="inv-price" oninput="updateInvEstimate()"><button class="ghost" type="button" onclick="this.closest('.inv-line').remove();updateInvEstimate()">✕</button></div>`;
      wrap.appendChild(r);
      updateInvEstimate();
    }
    function _invoiceLines() {
      return Array.from(document.querySelectorAll('#invLines .inv-line')).map((r) => ({
        exam_code: r.querySelector('.inv-code').value.trim() || null,
        label: r.querySelector('.inv-label').value.trim(),
        quantity: 1,
        unit_price_xof: r.querySelector('.inv-price').value || "0",
      })).filter((l) => l.label);
    }
    function updateInvEstimate() {
      const gross = _invoiceLines().reduce((s, l) => s + Number(l.unit_price_xof || 0), 0);
      const disc = Number($("invDiscount").value || 0);
      $("invEstimate").value = `${Math.max(0, gross - disc).toLocaleString("fr-FR")} FCFA`;
    }
    async function createInvoice(btn) {
      const lines = _invoiceLines();
      if (lines.length === 0) { showToast("Ajoutez au moins une ligne.", "error"); return; }
      const type = $("invPatientType").value;
      setLoading(btn, true);
      try {
        const inv = await api("/api/v1/invoices", {
          method: "POST", headers: headers(),
          body: JSON.stringify({
            patient_label: $("invPatientLabel").value || null,
            patient_type: type,
            insurance_id: type === "INSURED" ? ($("invInsuranceId").value || null) : null,
            lines, discount_xof: $("invDiscount").value || "0",
          }),
        });
        showToast(`Facture ${inv.invoice_number} émise.`, "success");
        $("invoiceResult").textContent = `Facture ${inv.invoice_number}\nNet : ${inv.net_total_xof} FCFA\nCNAM : ${inv.cnam_part_xof} FCFA\nReste patient : ${inv.patient_due_xof} FCFA`;
        $("payInvoiceId").value = inv.id;
        await Promise.all([loadInvoices(), loadFinanceSummary()]);
      } catch { showToast("Échec de l'émission.", "error"); }
      finally { setLoading(btn, false); }
    }
    async function loadInvoices() {
      const tbody = $("invoicesTable").querySelector("tbody");
      const st = $("invStatusFilter") ? $("invStatusFilter").value : "";
      try {
        const rows = _listItems(await api(`/api/v1/invoices${st ? "?status=" + st : ""}`, { headers: headers(false) }));
        if (rows.length === 0) { tbody.innerHTML = '<tr><td colspan="6" class="muted">Aucune facture.</td></tr>'; return; }
        tbody.innerHTML = rows.map((i) => {
          const canCancel = i.status !== "cancelled" && Number(i.paid_xof) === 0;
          // Plan BNPL proposé uniquement s'il reste à payer et qu'aucun plan n'existe.
          const canPlan = i.status !== "cancelled" && Number(i.balance_xof) > 0 && !i.payment_plan_id;
          return `<tr><td>${security.escapeHtml(i.invoice_number)}</td><td>${security.escapeHtml(i.patient_label || "—")}</td><td>${Number(i.net_total_xof).toLocaleString("fr-FR")}</td><td>${Number(i.balance_xof).toLocaleString("fr-FR")}</td><td>${_INV_STATUS_LABELS[i.status] || i.status}${i.payment_plan_id ? " · BNPL" : ""}</td><td><button class="ghost" onclick="selectInvoice(${i.id},${i.balance_xof})">Encaisser</button> <button class="ghost" onclick="openInvoiceReceipt(${i.id})">Reçu PDF</button>${canPlan ? ` <button class="ghost" onclick="createInvoicePaymentPlan(${i.id})">Échelonner</button>` : ""}${canCancel ? ` <button class="ghost" onclick="cancelInvoice(${i.id})">Annuler</button>` : ""}</td></tr>`;
        }).join("");
      } catch { tbody.innerHTML = '<tr><td colspan="6" class="muted">Indisponible.</td></tr>'; }
    }
    function selectInvoice(id, balance) { $("payInvoiceId").value = id; $("payAmount").value = balance; $("payAmount").focus(); }
    async function openInvoiceReceipt(id) {
      try {
        const resp = await fetch(`/api/v1/invoices/${id}/receipt.pdf`, { headers: headers(false) });
        if (!resp.ok) throw new Error();
        window.open(URL.createObjectURL(await resp.blob()), "_blank");
      } catch { showToast("Reçu indisponible.", "error"); }
    }
    async function createInvoicePaymentPlan(id) {
      // Optionnel : seulement si le patient ne peut pas régler comptant.
      const months = prompt("Échelonner le reste à charge sur combien de mois ? (2 à 24)\nÀ n'utiliser que si le patient ne peut pas payer comptant.", "3");
      if (!months) return;
      const n = parseInt(months, 10);
      if (!(n >= 2 && n <= 24)) { showToast("Indiquez un nombre de mois entre 2 et 24.", "error"); return; }
      try {
        const plan = await api(`/api/v1/invoices/${id}/payment-plan`, { method: "POST", headers: headers(), body: JSON.stringify({ installment_months: n }) });
        showToast(`Plan de paiement créé : ${plan.installment_months} échéances.`, "success");
        await Promise.all([loadInvoices(), loadFinanceSummary()]);
      } catch { showToast("Plan impossible (facture soldée ou plan déjà créé).", "error"); }
    }
    async function seedTariffs(btn) {
      setLoading(btn, true);
      try {
        const r = await api("/api/v1/tariffs/seed-defaults", { method: "POST", headers: headers() });
        showToast(`Tarifs initialisés (${r.created} examens ajoutés). Ajustez les prix au besoin.`, "success");
      } catch { showToast("Initialisation des tarifs impossible.", "error"); }
      finally { setLoading(btn, false); }
    }
    async function recordInvoicePayment(btn) {
      const id = $("payInvoiceId").value;
      const amount = $("payAmount").value;
      if (!id || !amount) { showToast("Facture et montant requis.", "error"); return; }
      setLoading(btn, true);
      try {
        const inv = await api(`/api/v1/invoices/${id}/payments`, {
          method: "POST", headers: headers(),
          body: JSON.stringify({ amount_xof: amount, method: $("payMethod").value, reference: $("payReference").value || null }),
        });
        showToast(`Paiement enregistré (${_INV_STATUS_LABELS[inv.status]}).`, "success");
        $("invoiceResult").textContent = `Facture ${inv.invoice_number}\nEncaissé : ${inv.paid_xof} FCFA\nReste : ${inv.balance_xof} FCFA\nStatut : ${_INV_STATUS_LABELS[inv.status]}`;
        await Promise.all([loadInvoices(), loadFinanceSummary()]);
      } catch { showToast("Échec de l'encaissement.", "error"); }
      finally { setLoading(btn, false); }
    }
    async function cancelInvoice(id) {
      if (!confirm("Annuler cette facture ?")) return;
      try {
        await api(`/api/v1/invoices/${id}/cancel`, { method: "POST", headers: headers() });
        showToast("Facture annulée.", "success");
        await Promise.all([loadInvoices(), loadFinanceSummary()]);
      } catch { showToast("Annulation impossible (déjà encaissée ?).", "error"); }
    }
    async function loadFinanceSummary() {
      try {
        const s = await api("/api/v1/invoices/summary", { headers: headers(false) });
        const fmt = (v) => Number(v || 0).toLocaleString("fr-FR");
        if ($("finNet")) $("finNet").textContent = fmt(s.net_total_xof);
        if ($("finCollected")) $("finCollected").textContent = fmt(s.collected_xof);
        if ($("finOutstanding")) $("finOutstanding").textContent = fmt(s.outstanding_xof);
        if ($("finCnam")) $("finCnam").textContent = fmt(s.cnam_part_xof);
        if ($("finCount")) $("finCount").textContent = s.invoice_count;
      } catch { /* résumé indisponible */ }
    }
    async function loadSamples() {
      const tbody = $("samplesTable").querySelector("tbody");
      loadingStates.showSkeleton(tbody, 5);
      try {
        // Fetch samples + patients en parallèle pour enrichir l'affichage et les caches
        const [samplesData, patientsData] = await Promise.all([
          api("/api/v1/samples", { headers: headers(false) }),
          api("/api/v1/patients", { headers: headers(false) }).catch(() => ({ items: [] })),
        ]);
        _patientsCache = {};
        _listItems(patientsData).forEach(p => { _patientsCache[p.id] = p; });
        _samplesCache = _listItems(samplesData);

        const rows = _samplesCache.map(s => {
          const p = _patientsCache[s.patient_id] || null;
          const pLabel = p
            ? security.escapeHtml(p.first_name + ' ' + p.last_name)
            : (s.patient_id ? '#' + s.patient_id : '—');
          const labelData = {
            barcode: s.barcode,
            patient: p ? (p.first_name + ' ' + p.last_name) : (s.patient_id ? 'Patient #' + s.patient_id : '—'),
            ipp:  p ? p.ipp_unique_id      : '',
            sex:  p ? (p.sex || '')        : '',
            dob:  p ? (p.birth_date || '') : '',
            date: s.collection_date ? s.collection_date.slice(0, 10) : '',
            exam: s.status || '',
          };
          // Workflow statut : Recu → En cours → Termine
          const STATUS_NEXT  = { 'Recu': 'En cours', 'En cours': 'Termine' };
          const STATUS_CLASS = { 'Recu': 'warn', 'En cours': '', 'Termine': 'ok', 'Annule': 'bad' };
          const STATUS_ICON  = { 'Recu': '📥', 'En cours': '⚗️', 'Termine': '✅', 'Annule': '❌' };
          const nextSt = STATUS_NEXT[s.status];
          const statusCell =
            `<span class="pill ${STATUS_CLASS[s.status] || ''}">${STATUS_ICON[s.status] || ''}${security.escapeHtml(s.status || '—')}</span>` +
            (nextSt
              ? ` <button class="ghost" style="font-size:11px;padding:3px 7px;" onclick="advanceSampleStatus(${s.id},'${nextSt}')">→ ${nextSt}</button>`
              : '');
          const tr = row(
            `<td>${s.id}</td>` +
            `<td><code style="font-size:11px;">${security.escapeHtml(s.barcode)}</code></td>` +
            `<td>${pLabel}</td>` +
            `<td style="white-space:nowrap;">${statusCell}</td>` +
            `<td><button class="ghost" title="Imprimer étiquette tube" onclick='printSampleLabel(${JSON.stringify(labelData)})'>🖨️</button></td>`
          );
          tr.dataset.sampleId = String(s.id);
          return tr;
        });
        setRows("samplesTable", rows);
      } catch (error) {
        tbody.innerHTML = '<tr><td colspan="5" style="text-align:center;color:var(--rose);">Erreur de chargement</td></tr>';
        throw error;
      }
    }
    async function createSample(btn) {
      return errorHandler.safeExecute(async () => {
        setLoading(btn, true);
        
        // Validate inputs
        const patientIdErrors = validator.validateField($("samplePatientId"), { required: true, numeric: true });
        const barcodeErrors = validator.validateField($("sampleBarcode"), { required: true, barcode: true });
        
        validator.showFieldErrors($("samplePatientId"), patientIdErrors);
        validator.showFieldErrors($("sampleBarcode"), barcodeErrors);
        
        if (patientIdErrors.length > 0 || barcodeErrors.length > 0) {
          throw new Error('Veuillez corriger les erreurs dans le formulaire');
        }
        
        if (!$("sampleBarcode").value) generateBarcode();
        
        const body = { 
          barcode: security.sanitize($("sampleBarcode").value), 
          patient_id: Number(security.sanitizeNumber($("samplePatientId").value)), 
          status: $("sampleStatus").value 
        };
        
        const created = await perfMonitor.measureAsync('createSample', () =>
          api("/api/v1/samples", { method: "POST", headers: headers(), body: JSON.stringify(body) })
        );
        
        $("resultSampleId").value = created.id;
        if ($("resultSampleBarcode")) $("resultSampleBarcode").value = created.barcode;
        if ($("resultSampleSelected")) $("resultSampleSelected").textContent = `✓ Échantillon #${created.id} (${created.barcode})`;
        $("imageBarcode").value = created.barcode;
        $("poctBarcode").value = created.barcode;
        showToast(`Échantillon ${security.escapeHtml(created.barcode)} créé avec succès`, "success");
        await loadSamples();
      }, 'createSample').finally(() => setLoading(btn, false));
    }
    // Flag colors: HH→dark red, H→rose, N→green, L→blue, LL→dark blue
    const _flagStyle = { HH: 'background:#7f1d1d;color:white', H: 'background:#be123c;color:white', N: 'background:#16a34a;color:white', L: 'background:#1d4ed8;color:white', LL: 'background:#1e1b4b;color:white' };
    function _flagBadge(analyte, flag) {
      const s = _flagStyle[flag] || 'background:#6b7280;color:white';
      return '<span class="pill" style="' + s + ';margin:1px;font-size:10px;" title="' + security.escapeHtml(analyte) + '">' + security.escapeHtml(analyte) + ':' + flag + '</span>';
    }
    function _listItems(payload) {
      if (Array.isArray(payload)) return payload;
      return payload?.items || [];
    }
    let _resultsCache = [];
    let _resultFilter = "all";
    let _resultSearch = "";
    let _resultSort = "date_desc";
    let _resultsViewCache = [];
    let _resultSampleById = {};
    let _resultPatientById = {};
    let _selectedResultDetail = null;
    function _resultValuePreview(value) {
      if (value && typeof value === "object" && !Array.isArray(value)) {
        if (value.label) return String(value.label);
        if (value.value !== undefined) return String(value.value) + (value.unit ? " " + value.unit : "");
        return "objet";
      }
      if (value === null || value === undefined || value === "") return "—";
      return String(value);
    }
    function _resultAnalyteBadges(r) {
      const dataPoints = r.data_points || {};
      const entries = Object.entries(dataPoints)
        .filter(([key]) => !["manual_entry_by", "entry_timestamp", "calibration", "overall_flags"].includes(key))
        .slice(0, 4);
      if (entries.length === 0) return '<span class="muted">Aucune donnée analytique</span>';
      return entries.map(([key, value]) => {
        const valueText = _resultValuePreview(value);
        const isCritical = Boolean(value && typeof value === "object" && value.is_critical);
        const status = value && typeof value === "object" && value.status ? String(value.status) : "";
        const style = isCritical
          ? "background:var(--rose);color:#fff;"
          : status && status !== "N"
            ? "background:var(--amber);color:#fff;"
            : "background:rgba(100,116,134,.14);color:var(--ink);";
        return `<span class="pill" style="${style};font-size:10px;" title="${security.escapeHtml(key)}">${security.escapeHtml(key)} ${security.escapeHtml(valueText)}</span>`;
      }).join("");
    }
    function _resultElapsedLabel(r) {
      if (!r.analysis_date) return "";
      const minutes = Math.max(0, Math.floor((Date.now() - new Date(r.analysis_date).getTime()) / 60000));
      if (!Number.isFinite(minutes)) return "";
      if (minutes < 60) return `${minutes} min`;
      if (minutes < 1440) return `${Math.floor(minutes / 60)} h`;
      return `${Math.floor(minutes / 1440)} j`;
    }
    function _resultMatchesFilter(r) {
      if (_resultFilter === "pending") return r.is_critical && !r.critical_ack_at;
      if (_resultFilter === "critical") return r.is_critical;
      if (_resultFilter === "unvalidated") return !r.is_validated;
      if (_resultFilter === "auto") return r.is_auto_validated;
      return true;
    }
    function _resultContext(r) {
      const sample = _resultSampleById[r.sample_id] || null;
      const patient = sample?.patient_id ? (_resultPatientById[sample.patient_id] || null) : null;
      return { sample, patient };
    }
    function _resultSearchText(r) {
      const { sample, patient } = _resultContext(r);
      const analytes = Object.keys(r.data_points || {}).join(" ");
      return [
        r.id,
        r.sample_id,
        sample?.barcode,
        patient?.ipp_unique_id,
        patient?.first_name,
        patient?.last_name,
        r.exam_code,
        analytes,
      ].filter(Boolean).join(" ").toLowerCase();
    }
    function _resultMatchesSearch(r) {
      if (!_resultSearch) return true;
      return _resultSearchText(r).includes(_resultSearch);
    }
    function _updateResultFilterButtons() {
      document.querySelectorAll("[data-result-filter]").forEach((btn) => {
        btn.classList.toggle("active", btn.dataset.resultFilter === _resultFilter);
      });
    }
    function setResultFilter(filter, btn = null) {
      _resultFilter = filter;
      if (btn) btn.classList.add("active");
      _updateResultFilterButtons();
      renderResultsTable();
    }
    function setResultSearch(value) {
      _resultSearch = String(value || "").trim().toLowerCase();
      renderResultsTable();
    }
    function setResultSort(value) {
      _resultSort = value || "date_desc";
      renderResultsTable();
    }
    function _resultPatientName(r) {
      const patient = _resultContext(r).patient;
      return patient ? [patient.first_name, patient.last_name].filter(Boolean).join(" ") : "";
    }
    function _resultSampleLabel(r) {
      return _resultContext(r).sample?.barcode || ("#" + r.sample_id);
    }
    function _sortResults(rows) {
      const sorted = [...rows];
      sorted.sort((a, b) => {
        if (_resultSort === "critical_first") {
          const ac = Number(Boolean(a.is_critical && !a.critical_ack_at));
          const bc = Number(Boolean(b.is_critical && !b.critical_ack_at));
          if (bc !== ac) return bc - ac;
        } else if (_resultSort === "patient_asc") {
          return _resultPatientName(a).localeCompare(_resultPatientName(b), "fr");
        } else if (_resultSort === "sample_asc") {
          return _resultSampleLabel(a).localeCompare(_resultSampleLabel(b), "fr");
        } else if (_resultSort === "validated_first") {
          const av = Number(Boolean(a.is_validated));
          const bv = Number(Boolean(b.is_validated));
          if (bv !== av) return bv - av;
        }
        return new Date(b.analysis_date || 0).getTime() - new Date(a.analysis_date || 0).getTime();
      });
      return sorted;
    }
    function renderResultsTable() {
      const rowsData = _sortResults(_resultsCache.filter(_resultMatchesFilter).filter(_resultMatchesSearch));
      _resultsViewCache = rowsData;
      const pendingCount = _resultsCache.filter((r) => r.is_critical && !r.critical_ack_at).length;
      const criticalCount = _resultsCache.filter((r) => r.is_critical).length;
      const unvalidatedCount = _resultsCache.filter((r) => !r.is_validated).length;
      if ($("resultsKpiPending")) $("resultsKpiPending").textContent = pendingCount;
      if ($("resultsKpiCritical")) $("resultsKpiCritical").textContent = criticalCount;
      if ($("resultsKpiUnvalidated")) $("resultsKpiUnvalidated").textContent = unvalidatedCount;
      if ($("resultsKpiLoaded")) $("resultsKpiLoaded").textContent = rowsData.length + "/" + _resultsCache.length;
      if ($("resultsListHint")) {
        $("resultsListHint").textContent = pendingCount > 0
          ? `${pendingCount} critique(s) à prendre en charge sur ${_resultsCache.length} résultat(s) chargés.`
          : `${_resultsCache.length} résultat(s) chargés, aucune critique en attente.`;
      }
      const rows = rowsData.map((r) => {
        const { sample, patient } = _resultContext(r);
        const patientName = patient ? [patient.first_name, patient.last_name].filter(Boolean).join(" ") : "";
        const sampleCell = '<strong>' + security.escapeHtml(sample?.barcode || ("#" + r.sample_id)) + '</strong>' +
          '<div class="result-staleness">' +
            security.escapeHtml(patientName || (sample?.patient_id ? "Patient #" + sample.patient_id : "Patient non renseigné")) +
            (patient?.ipp_unique_id ? ' · ' + security.escapeHtml(patient.ipp_unique_id) : '') +
          '</div>';
        let critCell = r.is_critical ? '<span class="pill bad">⛔ Critique</span>' : '<span style="color:var(--muted)">—</span>';
        if (r.delta_exceeded) critCell += ' <span class="pill" style="background:#b45309;color:white;font-size:10px;" title="Delta-check dépassé">△ Delta</span>';

        const flagsHtml = r.flags && Object.keys(r.flags).length > 0
          ? Object.entries(r.flags).map(([a, f]) => _flagBadge(a, f)).join('')
          : '<span style="color:var(--muted);font-size:11px;">—</span>';

        let ackCell;
        if (!r.is_critical) {
          ackCell = '<td style="color:var(--muted);font-size:11px;">—</td>';
        } else if (r.critical_ack_at) {
          const ts = new Date(r.critical_ack_at).toLocaleString("fr-FR", { dateStyle: "short", timeStyle: "short" });
          ackCell = '<td><span class="pill ok" title="Acquitté le ' + ts + '">✅ ' + ts + '</span></td>';
        } else {
          const elapsed = _resultElapsedLabel(r);
          ackCell = '<td><button class="danger" style="font-size:11px;padding:4px 9px;min-height:30px;" title="Confirmer que la valeur critique est prise en charge" onclick="ackCritical(' + r.id + ', this)">Prendre en charge</button>' +
            (elapsed ? '<div class="result-staleness">depuis ' + security.escapeHtml(elapsed) + '</div>' : '') +
            '</td>';
        }
        const autoCell = r.is_auto_validated
          ? '<span class="pill ok" title="Auto-validé ISO 15189 §5.8">🤖 Auto</span>'
          : '<span style="color:var(--muted);font-size:11px;">—</span>';
        const exam = r.exam_code ? '<div class="result-staleness">exam ' + security.escapeHtml(r.exam_code) + '</div>' : '';
        const tr = row(
          '<td><strong>#' + r.id + '</strong></td>' +
          '<td>' + sampleCell + '</td>' +
          '<td><div class="result-analytes">' + _resultAnalyteBadges(r) + '</div>' + exam + '</td>' +
          '<td>' + critCell + '</td>' +
          '<td style="white-space:nowrap;">' + flagsHtml + '</td>' +
          ackCell +
          '<td>' + (r.is_validated ? '<span class="pill ok">Oui</span>' : 'Non') + '</td>' +
          '<td>' + autoCell + '</td>' +
          '<td style="white-space:nowrap;">' +
            '<button class="ghost" onclick="openResultDetail(' + r.id + ')">Détail</button> ' +
            '<button class="ghost" onclick="openResultAuditFromList(' + r.id + ')">Audit</button> ' +
            '<button class="ghost" onclick="selectResult(' + r.id + ')">Utiliser</button> ' +
            '<button class="ghost" style="font-size:11px;padding:2px 8px;" onclick=\'openAmendPanel(' + r.id + ',' + JSON.stringify(r.data_points || {}) + ')\'>✏️</button>' +
          '</td>'
        );
        if (r.is_critical && !r.critical_ack_at) tr.classList.add('row-critical');
        else if (r.is_critical && r.critical_ack_at) tr.classList.add('row-warning');
        else if (r.delta_exceeded) tr.classList.add('row-warning');
        return tr;
      });
      setRows("resultsTable", rows);
    }
    async function loadResults() {
      const tbody = $("resultsTable").querySelector("tbody");
      loadingStates.showSkeleton(tbody, 5);

      try {
        const data = await api("/api/v1/results/cockpit?limit=100", { headers: headers(false) });
        const items = _listItems(data);
        _resultsCache = items.map((item) => item.result || item);
        _resultSampleById = {};
        _resultPatientById = {};
        items.forEach((item) => {
          if (item.sample) _resultSampleById[item.sample.id] = item.sample;
          if (item.patient) _resultPatientById[item.patient.id] = item.patient;
        });
        renderResultsTable();
      } catch (error) {
        tbody.innerHTML = '<tr><td colspan="9" style="text-align: center; color: var(--rose);">Erreur de chargement</td></tr>';
        throw error;
      }
    }
    function _csvCell(value) {
      const text = String(value ?? "");
      return '"' + text.replace(/"/g, '""') + '"';
    }
    function _resultExportRows() {
      return _resultsViewCache.map((r) => {
        const { sample, patient } = _resultContext(r);
        return {
          id: r.id,
          patient: patient ? [patient.first_name, patient.last_name].filter(Boolean).join(" ") : "",
          ipp: patient?.ipp_unique_id || "",
          barcode: sample?.barcode || "",
          exam: r.exam_code || "",
          analysis_date: r.analysis_date || "",
          critical: r.is_critical ? "oui" : "non",
          handled: r.critical_ack_at ? "oui" : "non",
          validated: r.is_validated ? "oui" : "non",
          auto_validated: r.is_auto_validated ? "oui" : "non",
          analytes: _resultPrimaryValues(r.data_points || {}, 12).join("; "),
        };
      });
    }
    function exportDisplayedResultsCsv() {
      const rows = _resultExportRows();
      if (rows.length === 0) { showToast("Aucun résultat affiché à exporter", "error"); return; }
      const headersCsv = ["id", "patient", "ipp", "barcode", "exam", "analysis_date", "critical", "handled", "validated", "auto_validated", "analytes"];
      const csv = "\ufeff" + headersCsv.join(",") + "\n" + rows.map((row) => headersCsv.map((key) => _csvCell(row[key])).join(",")).join("\n");
      const blob = new Blob([csv], { type: "text/csv;charset=utf-8" });
      const url = URL.createObjectURL(blob);
      const a = document.createElement("a");
      a.href = url;
      a.download = "ruggylab-resultats-affiches.csv";
      a.click();
      URL.revokeObjectURL(url);
      showToast("Export CSV généré", "success");
    }
    function printDisplayedResults() {
      const rows = _resultExportRows();
      if (rows.length === 0) { showToast("Aucun résultat affiché à imprimer", "error"); return; }
      const body = rows.map((row) => '<tr>' +
        '<td>#' + security.escapeHtml(row.id) + '</td>' +
        '<td>' + security.escapeHtml(row.patient || "—") + '<br><small>' + security.escapeHtml(row.ipp || "—") + '</small></td>' +
        '<td>' + security.escapeHtml(row.barcode || "—") + '</td>' +
        '<td>' + security.escapeHtml(row.exam || "—") + '</td>' +
        '<td>' + security.escapeHtml(_formatResultDate(row.analysis_date)) + '</td>' +
        '<td>' + security.escapeHtml(row.critical) + '</td>' +
        '<td>' + security.escapeHtml(row.analytes || "—") + '</td>' +
        '</tr>').join("");
      const win = window.open("", "_blank");
      if (!win) { showToast("Autorisez les popups pour générer le PDF", "error"); return; }
      win.document.write('<!doctype html><html><head><title>Résultats RuggyLab</title><style>body{font-family:Arial,sans-serif;margin:24px;color:#111827}table{width:100%;border-collapse:collapse;font-size:12px}th,td{border:1px solid #d1d5db;padding:7px;text-align:left;vertical-align:top}th{background:#eef2f7}h1{font-size:20px;margin:0 0 4px}.meta{color:#64748b;margin-bottom:16px}</style></head><body><h1>Résultats affichés</h1><div class="meta">RuggyLab OS · ' + security.escapeHtml(new Date().toLocaleString("fr-FR")) + '</div><table><thead><tr><th>ID</th><th>Patient</th><th>Échantillon</th><th>Examen</th><th>Date</th><th>Critique</th><th>Valeurs</th></tr></thead><tbody>' + body + '</tbody></table><script>window.print();<\\/script></body></html>');
      win.document.close();
    }
    async function ackDisplayedCriticals(btn) {
      const criticalRows = _resultsViewCache.filter((r) => r.is_critical && !r.critical_ack_at);
      const ids = criticalRows.map((r) => r.id);
      if (ids.length === 0) {
        showToast("Aucune valeur critique affichée à prendre en charge", "error");
        return;
      }
      if (_resultFilter === "all" && !_resultSearch && ids.length > 5) {
        showToast("Affinez la liste avant une prise en charge groupée de plus de 5 valeurs critiques", "error");
        return;
      }
      const patients = new Set();
      const samples = [];
      criticalRows.forEach((r) => {
        const { sample, patient } = _resultContext(r);
        const patientLabel = patient
          ? [patient.first_name, patient.last_name].filter(Boolean).join(" ") || patient.ipp_unique_id
          : "Patient non renseigné";
        patients.add(patientLabel || "Patient non renseigné");
        samples.push(sample?.barcode || ("#" + r.sample_id));
      });
      const visibleSamples = samples.slice(0, 6).join(", ") + (samples.length > 6 ? "…" : "");
      const message = [
        "Confirmer la prise en charge groupée ?",
        "",
        ids.length + " valeur(s) critique(s) affichée(s)",
        patients.size + " patient(s) concerné(s)",
        "Échantillons : " + visibleSamples,
        "",
        "Cette action sera tracée dans l'audit clinique."
      ].join("\n");
      if (!confirm(message)) return;
      if (btn) { btn.disabled = true; btn.textContent = "…"; }
      try {
        const response = await api("/api/v1/results/ack-critical-batch", {
          method: "PATCH",
          headers: headers(),
          body: JSON.stringify({ result_ids: ids }),
        });
        showToast((response.acknowledged || []).length + " valeur(s) critique(s) prise(s) en charge", "success");
        await loadResults();
        await loadPendingCriticals();
        await loadDashboard();
      } catch {
        showToast("Erreur lors de la prise en charge groupée", "error");
      } finally {
        if (btn) { btn.disabled = false; btn.textContent = "Prendre en charge affichés"; }
      }
    }
    async function ackCritical(resultId, btn) {
      if (btn) { btn.disabled = true; btn.textContent = "…"; }
      try {
        await api("/api/v1/results/" + resultId + "/ack-critical", { method: "PATCH", headers: headers() });
        showToast("Valeur critique prise en charge", "success");
        await loadResults();
        await loadPendingCriticals();
        await loadDashboard();
      } catch (e) {
        showToast("Erreur lors de la prise en charge", "error");
        if (btn) { btn.disabled = false; btn.textContent = "Prendre en charge"; }
      }
    }
    function selectResult(id) { $("reportResultId").value = id; $("malariaResultId").value = id; showView("reports"); }
    async function openResultAuditFromList(resultId) {
      await openResultDetail(resultId);
      $("resultDetailAudit")?.scrollIntoView({ behavior: "smooth", block: "start" });
    }
    function _resultStatusBadge(label, ok = false) {
      return ok ? '<span class="pill ok">' + security.escapeHtml(label) + '</span>' : '<span class="pill bad">' + security.escapeHtml(label) + '</span>';
    }
    function _formatResultDate(value) {
      if (!value) return "—";
      try { return new Date(value).toLocaleString("fr-FR", { dateStyle: "short", timeStyle: "short" }); }
      catch { return "—"; }
    }
    function _resultValueDetailRows(dataPoints) {
      const entries = Object.entries(dataPoints || {})
        .filter(([key]) => !["manual_entry_by", "entry_timestamp", "calibration", "overall_flags"].includes(key));
      if (entries.length === 0) return '<div class="empty-state">Aucune donnée analytique.</div>';
      return entries.map(([key, raw]) => {
        const valueText = _resultValuePreview(raw);
        const status = raw && typeof raw === "object" && raw.status ? String(raw.status) : "";
        const isCritical = Boolean(raw && typeof raw === "object" && raw.is_critical);
        const unit = "";
        const badge = isCritical
          ? '<span class="pill bad">Critique</span>'
          : status && status !== "N"
            ? '<span class="pill" style="background:var(--amber);color:#fff;">' + security.escapeHtml(status) + '</span>'
            : '<span class="pill ok">OK</span>';
        return '<div class="result-value-row">' +
          '<strong>' + security.escapeHtml(key) + '</strong>' +
          '<code>' + security.escapeHtml(valueText + unit) + '</code>' +
          badge +
          '</div>';
      }).join("");
    }
    function _renderBiorefDetail(outcome) {
      if (!outcome || outcome.mapped === false) {
        return '<div class="notice">Aucune interprétation bioref disponible pour ce résultat.</div>';
      }
      const components = outcome.components || [];
      if (components.length === 0) {
        return '<div class="notice">Référentiel trouvé, mais aucune valeur interprétable dans les données.</div>';
      }
      return '<div class="result-detail-values">' + components.map((c) => {
        const status = c.bioref_status || "—";
        const isBad = /CRITIQUE|BAS|HAUT|POSITIF/.test(status);
        return '<div class="result-value-row">' +
          '<strong>' + security.escapeHtml(c.component || c.canonical_code || c.test_code || "Test") + '</strong>' +
          '<span>' + security.escapeHtml(c.bioref_reference_range || "Référence non précisée") + '</span>' +
          (isBad ? '<span class="pill bad">' : '<span class="pill ok">') + security.escapeHtml(status) + '</span>' +
          '</div>';
      }).join("") + '</div>';
    }
    function _resultPrimaryValues(dataPoints, maxItems = 4) {
      return Object.entries(dataPoints || {})
        .filter(([key]) => !["manual_entry_by", "entry_timestamp", "calibration", "overall_flags"].includes(key))
        .slice(0, maxItems)
        .map(([key, raw]) => key + '=' + _resultValuePreview(raw));
    }
    function _formatResultDeltas(deltaMap) {
      const entries = Object.entries(deltaMap || {});
      if (entries.length === 0) return "—";
      return entries.slice(0, 4).map(([key, value]) => key + ' ' + (value > 0 ? '+' : '') + value).join(', ');
    }
    function _resultClinicalSummary(result, context, bioref, history) {
      const patient = _patientDisplayName(context.patient);
      const ipp = context.patient?.ipp_unique_id || "IPP non renseigné";
      const sample = context.sample?.barcode || (result.sample_id ? "échantillon #" + result.sample_id : "échantillon non renseigné");
      const values = _resultPrimaryValues(result.data_points || {}).join(', ') || "aucune valeur analytique";
      const biorefStatus = bioref?.components?.length
        ? bioref.components.map((c) => (c.component || c.canonical_code || c.test_code || "Test") + ": " + (c.bioref_status || "—")).join(', ')
        : (result.bioref_status || bioref?.bioref_status || "interprétation bioref non disponible");
      const critical = result.is_critical
        ? (result.critical_ack_at ? "critique pris en charge" : "critique à prendre en charge")
        : "non critique";
      const delta = result.delta_exceeded
        ? "delta-check dépassé" + (result.delta_analytes ? " (" + _formatResultDeltas(result.delta_analytes) + ")" : "")
        : "pas de delta-check signalé";
      const historyCount = history?.items?.length || 0;
      return [
        "Patient " + patient + " (" + ipp + ")",
        sample,
        "résultat #" + result.id + (result.exam_code ? " · " + result.exam_code : ""),
        values,
        critical,
        delta,
        biorefStatus,
        historyCount + " antériorité(s) comparable(s)"
      ].join(" · ");
    }
    function _renderResultHistory(history) {
      const items = history?.items || [];
      if (items.length === 0) {
        return '<div class="empty-state">Aucune antériorité comparable pour ce patient.</div>';
      }
      return '<table class="compact-mobile-table"><thead><tr><th>Date</th><th>Échantillon</th><th>Valeurs</th><th>Delta</th><th>Statut</th></tr></thead><tbody>' +
        items.map((item) => {
          const result = item.result || {};
          const sample = item.sample || {};
          const status = result.is_critical
            ? '<span class="pill bad">Critique</span>'
            : result.delta_exceeded
              ? '<span class="pill" style="background:var(--amber);color:#fff;">Delta</span>'
              : '<span class="pill ok">OK</span>';
          return '<tr>' +
            '<td>' + security.escapeHtml(_formatResultDate(result.analysis_date)) + '</td>' +
            '<td>' + security.escapeHtml(sample.barcode || ("#" + result.sample_id)) + '</td>' +
            '<td>' + security.escapeHtml(_resultPrimaryValues(result.data_points || {}, 3).join(', ') || '—') + '</td>' +
            '<td>' + security.escapeHtml(_formatResultDeltas(item.delta_from_current || {})) + '</td>' +
            '<td>' + status + '</td>' +
            '</tr>';
        }).join("") + '</tbody></table>';
    }
    function _renderResultClinicalAudit(events) {
      if (!events || events.length === 0) {
        return '<div class="empty-state">Aucune trace clinique liée à ce résultat.</div>';
      }
      return '<table class="compact-mobile-table"><thead><tr><th>Date</th><th>Action</th><th>Agent</th><th>Détail</th></tr></thead><tbody>' +
        events.map((event) => '<tr>' +
          '<td>' + security.escapeHtml(_formatResultDate(event.created_at)) + '</td>' +
          '<td>' + security.escapeHtml(event.event_type || '—') + '</td>' +
          '<td>' + security.escapeHtml(event.username || '—') + '</td>' +
          '<td><code style="font-size:11px;">' + security.escapeHtml(event.payload || '—') + '</code></td>' +
          '</tr>').join("") + '</tbody></table>';
    }
    function _patientDisplayName(patient) {
      if (!patient) return "—";
      const name = [patient.first_name, patient.last_name].filter(Boolean).join(" ").trim();
      return name || ("Patient #" + patient.id);
    }
    async function _loadResultContext(result) {
      const context = { sample: null, patient: null };
      if (!result?.sample_id) return context;
      try {
        const samples = await api('/api/v1/samples', { headers: headers(false) });
        context.sample = (samples || []).find((sample) => Number(sample.id) === Number(result.sample_id)) || null;
      } catch {}
      if (context.sample?.patient_id) {
        try {
          context.patient = await api('/api/v1/patients/' + context.sample.patient_id, { headers: headers(false) });
        } catch {}
      }
      return context;
    }
    async function openResultDetail(resultId) {
      try {
        let detail = null;
        try { detail = await api('/api/v1/results/' + resultId + '/detail', { headers: headers(false) }); } catch {}
        const result = detail?.result || await api('/api/v1/results/' + resultId, { headers: headers(false) });
        let bioref = detail?.bioref || null;
        if (!detail) {
          try { bioref = await api('/api/v1/results/' + resultId + '/bioref', { headers: headers(false) }); } catch {}
        }
        let history = { items: [] };
        try { history = await api('/api/v1/results/' + resultId + '/history?limit=5', { headers: headers(false) }); } catch {}
        let clinicalAudit = [];
        try { clinicalAudit = await api('/api/v1/results/' + resultId + '/clinical-audit?limit=20', { headers: headers(false) }); } catch {}
        const context = detail
          ? { sample: detail.sample || null, patient: detail.patient || null }
          : await _loadResultContext(result);
        _selectedResultDetail = { result, bioref, history, clinicalAudit, sample: context.sample, patient: context.patient };
        $('resultDetailTitle').textContent = '#' + result.id;
        $('resultDetailPatient').textContent = _patientDisplayName(context.patient);
        $('resultDetailIpp').textContent = context.patient?.ipp_unique_id || (context.sample?.patient_id ? 'Patient #' + context.sample.patient_id : '—');
        $('resultDetailSample').textContent = result.sample_id ? '#' + result.sample_id : '—';
        $('resultDetailBarcode').textContent = context.sample?.barcode || '—';
        $('resultDetailExam').textContent = result.exam_code || '—';
        $('resultDetailCritical').innerHTML = result.is_critical
          ? result.critical_ack_at
            ? _resultStatusBadge('Pris en charge', true)
            : _resultStatusBadge('À prendre en charge')
          : '<span class="pill ok">Non critique</span>';
        $('resultDetailValidation').innerHTML = result.is_validated
          ? '<span class="pill ok">Validé</span>'
          : '<span class="pill" style="background:var(--amber);color:#fff;">Non validé</span>';
        $('resultDetailValues').innerHTML = _resultValueDetailRows(result.data_points || {});
        $('resultDetailBioref').innerHTML = _renderBiorefDetail(bioref);
        $('resultDetailClinicalSummary').textContent = _resultClinicalSummary(result, context, bioref, history);
        $('resultDetailHistory').innerHTML = _renderResultHistory(history);
        $('resultDetailAudit').innerHTML = _renderResultClinicalAudit(clinicalAudit);
        $('resultDetailTrace').innerHTML =
          'Analyse: <strong>' + security.escapeHtml(_formatResultDate(result.analysis_date)) + '</strong>' +
          ' · Bio-validation: <strong>' + security.escapeHtml(_formatResultDate(result.bio_validated_at)) + '</strong>' +
          ' · Auto §5.8: <strong>' + (result.is_auto_validated ? 'oui' : 'non') + '</strong>' +
          (context.sample?.status ? ' · Statut échantillon: <strong>' + security.escapeHtml(context.sample.status) + '</strong>' : '') +
          (context.sample?.collection_date ? ' · Prélèvement: <strong>' + security.escapeHtml(_formatResultDate(context.sample.collection_date)) + '</strong>' : '') +
          (context.sample?.received_date ? ' · Réception: <strong>' + security.escapeHtml(_formatResultDate(context.sample.received_date)) + '</strong>' : '') +
          (result.amendment_reason ? '<br>Dernière correction: ' + security.escapeHtml(result.amendment_reason) : '');
        const ackBtn = $('resultDetailAckBtn');
        if (ackBtn) {
          ackBtn.style.display = result.is_critical && !result.critical_ack_at ? '' : 'none';
          ackBtn.textContent = 'Prendre en charge';
        }
        $('resultDetailPanel').style.display = 'block';
        $('resultDetailPanel').scrollIntoView({ behavior: 'smooth', block: 'start' });
      } catch (e) {
        showToast('Erreur chargement détail résultat', 'error');
      }
    }
    function closeResultDetail() {
      _selectedResultDetail = null;
      const panel = $('resultDetailPanel');
      if (panel) panel.style.display = 'none';
    }
    async function ackCriticalFromDetail(btn) {
      if (!_selectedResultDetail?.result?.id) return;
      await ackCritical(_selectedResultDetail.result.id, btn);
      await openResultDetail(_selectedResultDetail.result.id);
    }
    function useDetailedResult() {
      if (!_selectedResultDetail?.result?.id) return;
      selectResult(_selectedResultDetail.result.id);
    }
    async function copyResultClinicalSummary() {
      const summary = $('resultDetailClinicalSummary')?.textContent?.trim();
      if (!summary) { showToast('Aucune synthèse à copier', 'error'); return; }
      try {
        await navigator.clipboard.writeText(summary);
        showToast('Synthèse résultat copiée', 'success');
      } catch {
        showToast('Copie indisponible dans ce navigateur', 'error');
      }
    }
    async function openDetailedResultFhir() {
      if (!_selectedResultDetail?.result?.id) return;
      try {
        const resultId = _selectedResultDetail.result.id;
        const resp = await fetch(normalizeApiPath(`/api/v1/results/${resultId}/fhir`), { headers: headers(false) });
        if (!resp.ok) { showToast('Export FHIR résultat indisponible', 'error'); return; }
        const blob = await resp.blob();
        const url = URL.createObjectURL(blob);
        const a = document.createElement('a');
        a.href = url; a.download = `result-${resultId}-diagnostic-report.fhir.json`; a.click();
        URL.revokeObjectURL(url);
        showToast('FHIR résultat téléchargé', 'success');
      } catch {
        showToast('Erreur export FHIR résultat', 'error');
      }
    }
    function templateDataPoints() {
      const values = {};
      document.querySelectorAll("#dataPoints input[data-result-key], #resultFields input[data-result-key]")
        .forEach((input) => {
          const raw = input.value.trim();
          if (raw === "") return;
          const numeric = Number(raw);
          values[input.dataset.resultKey] = Number.isNaN(numeric) ? raw : numeric;
        });
      return values;
    }
    async function createResult(btn) {
      return errorHandler.safeExecute(async () => {
        setLoading(btn, true);
        
        // Validate inputs
        const sampleIdErrors = validator.validateField($("resultSampleId"), { required: true, numeric: true });
        const equipmentIdErrors = validator.validateField($("resultEquipmentId"), { numeric: true });
        
        validator.showFieldErrors($("resultSampleId"), sampleIdErrors);
        validator.showFieldErrors($("resultEquipmentId"), equipmentIdErrors);
        
        if (sampleIdErrors.length > 0) {
          throw new Error('Veuillez corriger les erreurs dans le formulaire');
        }
        
        // Validate result fields
        const resultFields = document.querySelectorAll("#dataPoints input[data-result-key]");
        let hasResultErrors = false;
        
        resultFields.forEach(input => {
          const value = input.value.trim();
          if (value && isNaN(Number(value))) {
            input.classList.add('error-input');
            hasResultErrors = true;
          } else {
            input.classList.remove('error-input');
          }
        });
        
        if (hasResultErrors) {
          throw new Error('Les valeurs des résultats doivent être numériques');
        }
        
        const body = { 
          sample_id: Number(security.sanitizeNumber($("resultSampleId").value)), 
          equipment_id: $("resultEquipmentId").value ? Number(security.sanitizeNumber($("resultEquipmentId").value)) : null, 
          data_points: templateDataPoints(), 
          is_critical: false 
        };
        
        await perfMonitor.measureAsync('createResult', () =>
          api("/api/v1/results", { method: "POST", headers: headers(), body: JSON.stringify(body) })
        );
        
        showToast("Résultat créé et validé avec succès", "success");
        await loadResults();
      }, 'createResult').finally(() => setLoading(btn, false));
    }
    async function ingestDh36(btn) {
      setLoading(btn, true);
      try {
        const data = await api("/api/v1/dh36/ingest", { method: "POST", headers: headers(), body: JSON.stringify({ raw_message: $("hl7Message").value }) });
        showToast("Message DH36 traité avec succès", "success");
        $("hl7Message").value = "";
      } catch (e) {
        showToast("Erreur lors du traitement DH36", "error");
      } finally {
        setLoading(btn, false);
      }
    }
    async function submitPoct(btn) {
      setLoading(btn, true);
      try {
        const body = { sample_barcode: $("poctBarcode").value, equipment_serial: $("poctSerial").value, glucose_raw: Number($("poctGlucose").value), cholesterol_raw: Number($("poctChol").value), uric_acid_raw: Number($("poctUa").value), lactate_raw: 1.2, ketones_raw: 0.2 };
        await api("/api/v1/results/precis-expert", { method: "POST", headers: headers(), body: JSON.stringify(body) });
        showToast("Résultat POCT enregistré avec succès", "success");
      } catch (e) {
        showToast("Erreur lors de l'enregistrement POCT", "error");
      } finally {
        setLoading(btn, false);
      }
    }
    async function reserveImage(btn) {
      setLoading(btn, true);
      try {
        const data = await api("/api/v1/imaging/capture-microscope", { method: "POST", headers: headers(), body: JSON.stringify({ sample_barcode: $("imageBarcode").value }) });
        $("malariaResultId").value = data.result_id;
        showToast("Image réservée avec succès", "success");
      } catch (e) {
        showToast("Erreur lors de la réservation d'image", "error");
      } finally {
        setLoading(btn, false);
      }
    }
    async function enqueueMalaria(btn) {
      setLoading(btn, true);
      try {
        const data = await api(`/api/v1/imaging/malaria/analyze/${$("malariaResultId").value}`, { method: "POST", headers: headers(false) });
        $("malariaJobId").value = data.id;
        showToast("Analyse paludisme mise en file d'attente", "success");
      } catch (e) {
        showToast("Erreur lors de la mise en file d'attente", "error");
      } finally {
        setLoading(btn, false);
      }
    }
    async function processMalaria(btn) {
      setLoading(btn, true);
      try {
        await api(`/api/v1/imaging/malaria/jobs/${$("malariaJobId").value}/process`, { method: "POST", headers: headers(false) });
        showToast("Analyse paludisme traitée avec succès", "success");
      } catch (e) {
        showToast("Erreur lors du traitement de l'analyse", "error");
      } finally {
        setLoading(btn, false);
      }
    }
    // ══════════════════════════════════════════════════════════════
    //  Seuils critiques (panic values)
    // ══════════════════════════════════════════════════════════════
    async function loadCriticalRanges() {
      const data = await api('/api/v1/critical-ranges', { headers: headers(false) });
      setRows('criticalRangesTable', data.map(function(cr) {
        return row(
          '<td><strong>' + security.escapeHtml(cr.analyte) + '</strong></td>' +
          '<td style="color:#be123c;">' + (cr.low_critical !== null ? cr.low_critical : '<span style="color:var(--muted);">—</span>') + '</td>' +
          '<td style="color:#be123c;">' + (cr.high_critical !== null ? cr.high_critical : '<span style="color:var(--muted);">—</span>') + '</td>' +
          '<td style="color:var(--muted);font-size:11px;">' + security.escapeHtml(cr.unit || '—') + '</td>' +
          '<td><button class="ghost" style="color:#be123c;font-size:11px;" onclick="deleteCriticalRange(' + cr.id + ')">✕</button></td>'
        );
      }));
    }

    async function createCriticalRange(btn) {
      setLoading(btn, true);
      try {
        const analyte = $('crAnalyte').value.trim();
        const lowVal  = $('crLow').value.trim();
        const highVal = $('crHigh').value.trim();
        if (!analyte) throw new Error('Analyte obligatoire');
        if (!lowVal && !highVal) throw new Error('Au moins un seuil (bas ou haut) requis');
        await api('/api/v1/critical-ranges', {
          method: 'POST', headers: headers(),
          body: JSON.stringify({
            analyte: analyte,
            unit:  $('crUnit').value.trim(),
            low_critical:  lowVal  !== '' ? Number(lowVal)  : null,
            high_critical: highVal !== '' ? Number(highVal) : null,
          })
        });
        showToast('Seuil critique enregistré', 'success');
        ['crAnalyte','crUnit','crLow','crHigh'].forEach(function(id){ $(id).value = ''; });
        await loadCriticalRanges();
      } catch(e) {
        showToast(e.message || 'Erreur', 'error');
      } finally {
        setLoading(btn, false);
      }
    }

    async function deleteCriticalRange(id) {
      if (!confirm('Désactiver ce seuil critique ?')) return;
      try {
        await api('/api/v1/critical-ranges/' + id, { method: 'DELETE', headers: headers() });
        showToast('Seuil désactivé', 'success');
        await loadCriticalRanges();
      } catch(e) {
        showToast(e.message || 'Erreur', 'error');
      }
    }

    // ══════════════════════════════════════════════════════════════
    //  Delta-check rules
    // ══════════════════════════════════════════════════════════════
    async function loadDeltaRules() {
      try {
        const data = await api('/api/v1/delta-check-rules', { headers: headers(false) });
        setRows('deltaRulesTable', data.map(function(r) {
          return row(
            '<td><strong>' + security.escapeHtml(r.analyte) + '</strong></td>' +
            '<td style="text-align:center;">' + (r.delta_abs !== null && r.delta_abs !== undefined ? r.delta_abs : '—') + '</td>' +
            '<td style="text-align:center;">' + (r.delta_pct !== null && r.delta_pct !== undefined ? r.delta_pct + ' %' : '—') + '</td>' +
            '<td style="text-align:center;">' + r.lookback_days + ' j</td>' +
            '<td style="color:var(--muted);">' + security.escapeHtml(r.unit || '—') + '</td>' +
            '<td><button class="ghost" style="font-size:11px;color:#b45309;" onclick="deleteDeltaRule(' + r.id + ')">✕</button></td>'
          );
        }));
      } catch(e) { /* ignore */ }
    }
    async function createDeltaRule(btn) {
      setLoading(btn, true);
      try {
        const body = { analyte: $('dcAnalyte').value.trim(), unit: $('dcUnit').value.trim(), lookback_days: Number($('dcLookback').value) || 30 };
        if ($('dcAbs').value) body.delta_abs = Number($('dcAbs').value);
        if ($('dcPct').value) body.delta_pct = Number($('dcPct').value);
        await api('/api/v1/delta-check-rules', { method: 'POST', headers: headers(), body: JSON.stringify(body) });
        showToast('Règle delta-check enregistrée', 'success');
        ['dcAnalyte','dcUnit','dcAbs','dcPct'].forEach(function(id){ $(id).value = ''; });
        $('dcLookback').value = '30';
        await loadDeltaRules();
      } catch(e) { showToast(e.message || 'Erreur', 'error'); }
      finally { setLoading(btn, false); }
    }
    async function deleteDeltaRule(id) {
      if (!confirm('Désactiver cette règle delta-check ?')) return;
      try {
        await api('/api/v1/delta-check-rules/' + id, { method: 'DELETE', headers: headers() });
        showToast('Règle désactivée', 'success');
        await loadDeltaRules();
      } catch(e) { showToast(e.message || 'Erreur', 'error'); }
    }

    // ══════════════════════════════════════════════════════════════
    //  Valeurs de référence (HH/H/N/L/LL)
    // ══════════════════════════════════════════════════════════════
    async function loadRefRanges() {
      try {
        const data = await api('/api/v1/reference-ranges', { headers: headers(false) });
        setRows('refRangesTable', data.map(function(r) {
          const age = (r.age_min_years !== null && r.age_min_years !== undefined) || (r.age_max_years !== null && r.age_max_years !== undefined)
            ? (r.age_min_years !== null && r.age_min_years !== undefined ? r.age_min_years : '0') + '–' + (r.age_max_years !== null && r.age_max_years !== undefined ? r.age_max_years : '∞') + ' ans'
            : '—';
          return row(
            '<td><strong>' + security.escapeHtml(r.analyte) + '</strong></td>' +
            '<td style="text-align:center;">' + r.sex + '</td>' +
            '<td style="text-align:center;font-size:11px;">' + age + '</td>' +
            '<td style="text-align:center;color:#1d4ed8;">' + (r.low_normal !== null && r.low_normal !== undefined ? r.low_normal : '—') + '</td>' +
            '<td style="text-align:center;color:#be123c;">' + (r.high_normal !== null && r.high_normal !== undefined ? r.high_normal : '—') + '</td>' +
            '<td style="color:var(--muted);">' + security.escapeHtml(r.unit || '—') + '</td>' +
            '<td><button class="ghost" style="font-size:11px;" onclick="deleteRefRange(' + r.id + ')">✕</button></td>'
          );
        }));
      } catch(e) { /* ignore */ }
    }
    async function createRefRange(btn) {
      setLoading(btn, true);
      try {
        const body = { analyte: $('rrAnalyte').value.trim(), sex: $('rrSex').value, unit: $('rrUnit').value.trim() };
        if ($('rrLow').value) body.low_normal = Number($('rrLow').value);
        if ($('rrHigh').value) body.high_normal = Number($('rrHigh').value);
        if ($('rrAgeMin').value) body.age_min_years = Number($('rrAgeMin').value);
        if ($('rrAgeMax').value) body.age_max_years = Number($('rrAgeMax').value);
        await api('/api/v1/reference-ranges', { method: 'POST', headers: headers(), body: JSON.stringify(body) });
        showToast('Plage de référence enregistrée', 'success');
        ['rrAnalyte','rrUnit','rrLow','rrHigh','rrAgeMin','rrAgeMax'].forEach(function(id){ $(id).value = ''; });
        $('rrSex').value = '*';
        await loadRefRanges();
      } catch(e) { showToast(e.message || 'Erreur', 'error'); }
      finally { setLoading(btn, false); }
    }
    async function deleteRefRange(id) {
      if (!confirm('Désactiver cette plage de référence ?')) return;
      try {
        await api('/api/v1/reference-ranges/' + id, { method: 'DELETE', headers: headers() });
        showToast('Plage désactivée', 'success');
        await loadRefRanges();
      } catch(e) { showToast(e.message || 'Erreur', 'error'); }
    }

    // ══════════════════════════════════════════════════════════════
    //  Alertes critiques — config + pending + notification
    // ══════════════════════════════════════════════════════════════
    async function loadNotifConfigs() {
      try {
        const data = await api('/api/v1/critical-alerts/config', { headers: headers(false) });
        setRows('notifConfigsTable', data.map(function(c) {
          return row(
            '<td style="font-size:11px;word-break:break-all;">' + security.escapeHtml(c.webhook_url || c.email || '—') + '</td>' +
            '<td style="text-align:center;">' + c.delay_minutes + ' min</td>' +
            '<td><button class="ghost" style="font-size:11px;color:#be123c;" onclick="deleteNotifConfig(' + c.id + ')">✕</button></td>'
          );
        }));
      } catch(e) { /* ignore */ }
    }
    async function createNotifConfig(btn) {
      setLoading(btn, true);
      try {
        const body = { delay_minutes: Number($('notifDelay').value) || 30 };
        if ($('notifWebhook').value) body.webhook_url = $('notifWebhook').value.trim();
        await api('/api/v1/critical-alerts/config', { method: 'POST', headers: headers(), body: JSON.stringify(body) });
        showToast('Configuration de notification enregistrée', 'success');
        $('notifWebhook').value = '';
        await loadNotifConfigs();
      } catch(e) { showToast(e.message || 'Erreur', 'error'); }
      finally { setLoading(btn, false); }
    }
    async function deleteNotifConfig(id) {
      if (!confirm('Désactiver cette configuration ?')) return;
      try {
        await api('/api/v1/critical-alerts/config/' + id, { method: 'DELETE', headers: headers() });
        showToast('Configuration désactivée', 'success');
        await loadNotifConfigs();
      } catch(e) { showToast(e.message || 'Erreur', 'error'); }
    }
    async function loadPendingCriticals() {
      try {
        const data = await api('/api/v1/critical-alerts/pending', { headers: headers(false) });
        const badge = $('pendingBadge');
        if (badge) { badge.style.display = data.length > 0 ? '' : 'none'; badge.textContent = data.length; }
        const div = $('pendingCriticalsDiv');
        if (!div) return;
        if (data.length === 0) { div.innerHTML = '<p style="color:var(--muted);font-size:12px;">Aucun résultat critique en attente.</p>'; return; }
        div.innerHTML = '<table style="font-size:11px;width:100%;"><thead><tr><th>Résultat</th><th>Échantillon</th><th>Écoulé</th><th>Statut</th></tr></thead><tbody>' +
          data.map(function(p) {
            const rowBg = p.overdue ? '#fee2e2' : '#fef3c7';
            return '<tr style="background:' + rowBg + ';"><td>' + p.result_id + '</td><td>' + p.sample_id + '</td><td>' + p.elapsed_minutes + ' min</td><td>' +
              (p.overdue ? '<span class="pill bad">En retard</span>' : '<span style="color:#ca8a04;">En attente</span>') + '</td></tr>';
          }).join('') + '</tbody></table>';
      } catch(e) { /* ignore */ }
    }
    async function checkAndNotify(btn) {
      setLoading(btn, true);
      try {
        const result = await api('/api/v1/critical-alerts/check', { method: 'POST', headers: headers() });
        showToast('Vérification : ' + result.notified + ' notifiés, ' + result.pending + ' en attente', result.pending > 0 ? 'error' : 'success');
        await loadPendingCriticals();
      } catch(e) { showToast(e.message || 'Erreur', 'error'); }
      finally { setLoading(btn, false); }
    }

    // ══════════════════════════════════════════════════════════════
    //  Rapport QC mensuel
    // ══════════════════════════════════════════════════════════════
    function openQcReport() {
      const year = $('qcReportYear') ? $('qcReportYear').value || new Date().getFullYear() : new Date().getFullYear();
      const month = $('qcReportMonth') ? $('qcReportMonth').value || (new Date().getMonth() + 1) : (new Date().getMonth() + 1);
      const authHeader = headers(false);
      const tok = authHeader['Authorization'] ? authHeader['Authorization'].replace('Bearer ', '') : '';
      // Fetch the report HTML and open it in a new tab
      fetch('/api/v1/reports/qc-report?year=' + year + '&month=' + month, { headers: authHeader })
        .then(function(r) { return r.text(); })
        .then(function(html) {
          const w = window.open('', '_blank');
          if (w) { w.document.write(html); w.document.close(); }
          else { showToast('Autorisez les popups pour ouvrir le rapport', 'error'); }
        })
        .catch(function() { showToast('Erreur lors du chargement du rapport QC', 'error'); });
    }

    // ══════════════════════════════════════════════════════════════
    //  QC Analytique — Westgard / Levey-Jennings
    // ══════════════════════════════════════════════════════════════
    let _qcSelectedControl = null;

    function _ljSvg(control, results) {
      const N = results.length;
      const mean = control.target_mean;
      const sd   = control.target_sd;
      const W = 640, H = 220;
      const P = { top: 14, right: 38, bottom: 38, left: 58 };
      const w = W - P.left - P.right;
      const h = H - P.top - P.bottom;
      const yMin = mean - 3.6 * sd;
      const yMax = mean + 3.6 * sd;
      const yPx = v => P.top + h * (1 - (v - yMin) / (yMax - yMin));
      const xPx = i => N <= 1 ? P.left + w / 2 : P.left + (i / (N - 1)) * w;
      const REJECT_RULES = ['1-3s','2-2s','R-4s','4-1s','10x'];

      let svg = '<svg viewBox="0 0 ' + W + ' ' + H + '" width="100%" style="max-height:220px;display:block;font-family:Arial,Helvetica,sans-serif;">';

      // background bands
      svg += '<rect x="' + P.left + '" y="' + yPx(mean+3*sd) + '" width="' + w + '" height="' + (yPx(mean-3*sd)-yPx(mean+3*sd)) + '" fill="#fef2f2"/>';
      svg += '<rect x="' + P.left + '" y="' + yPx(mean+2*sd) + '" width="' + w + '" height="' + (yPx(mean-2*sd)-yPx(mean+2*sd)) + '" fill="#fffbeb"/>';
      svg += '<rect x="' + P.left + '" y="' + yPx(mean+sd)   + '" width="' + w + '" height="' + (yPx(mean-sd)  -yPx(mean+sd))   + '" fill="#f0fdf4"/>';

      // horizontal rules
      [
        { v: mean+3*sd, c:'#dc2626', d:'5,3', l:'+3s' },
        { v: mean+2*sd, c:'#f59e0b', d:'4,3', l:'+2s' },
        { v: mean+sd,   c:'#86efac', d:'2,3', l:'+1s' },
        { v: mean,      c:'#16a34a', d:'',    l:'x̅'  },
        { v: mean-sd,   c:'#86efac', d:'2,3', l:'-1s' },
        { v: mean-2*sd, c:'#f59e0b', d:'4,3', l:'-2s' },
        { v: mean-3*sd, c:'#dc2626', d:'5,3', l:'-3s' },
      ].forEach(function(r) {
        var y = yPx(r.v);
        var da = r.d ? ' stroke-dasharray="' + r.d + '"' : '';
        svg += '<line x1="' + P.left + '" y1="' + y + '" x2="' + (P.left+w) + '" y2="' + y + '" stroke="' + r.c + '" stroke-width="1"' + da + '/>';
        svg += '<text x="' + (P.left-4) + '" y="' + (y+4) + '" text-anchor="end" font-size="9" fill="#6b7280">' + r.v.toFixed(1) + '</text>';
        svg += '<text x="' + (P.left+w+4) + '" y="' + (y+4) + '" font-size="9" fill="#6b7280">' + r.l + '</text>';
      });

      // connecting line
      if (N > 1) {
        var path = 'M ' + xPx(0) + ' ' + yPx(results[0].value);
        for (var i = 1; i < N; i++) path += ' L ' + xPx(i) + ' ' + yPx(results[i].value);
        svg += '<path d="' + path + '" fill="none" stroke="#94a3b8" stroke-width="1.5"/>';
      }

      // points + x-axis labels
      var step = N <= 12 ? 1 : Math.ceil(N / 12);
      results.forEach(function(r, i) {
        var x = xPx(i), y = yPx(r.value);
        var v = r.violations || [];
        var col = v.some(function(x){return REJECT_RULES.includes(x);}) ? '#dc2626'
                : v.includes('1-2s') ? '#f59e0b' : '#16a34a';
        svg += '<circle cx="' + x + '" cy="' + y + '" r="5" fill="' + col + '" stroke="white" stroke-width="1.5"><title>' + r.measured_at + (v.length ? ' ⚠ ' + v.join(', ') : ' ✓') + '</title></circle>';
        if (i % step === 0) {
          var lbl = r.measured_at ? r.measured_at.slice(5) : '';
          svg += '<text x="' + x + '" y="' + (H-P.bottom+14) + '" text-anchor="middle" font-size="9" fill="#6b7280" transform="rotate(-40,' + x + ',' + (H-P.bottom+14) + ')">' + lbl + '</text>';
        }
      });

      svg += '<rect x="' + P.left + '" y="' + P.top + '" width="' + w + '" height="' + h + '" fill="none" stroke="#e2e8f0" stroke-width="1"/>';
      svg += '</svg>';
      return svg;
    }

    async function loadQc() {
      const controls = await api('/api/v1/qc/controls', { headers: headers(false) });
      setRows('qcControlsTable', controls.map(function(c) {
        var active = _qcSelectedControl && _qcSelectedControl.id === c.id;
        var tr = row(
          '<td><strong>' + security.escapeHtml(c.analyte) + '</strong></td>' +
          '<td>' + security.escapeHtml(c.level) + '</td>' +
          '<td>' + c.target_mean + '</td>' +
          '<td>' + c.target_sd + '</td>' +
          '<td style="color:var(--muted);">' + security.escapeHtml(c.unit || '—') + '</td>' +
          '<td style="white-space:nowrap;">' +
            '<button class="ghost" onclick=\'selectQcControl(' + JSON.stringify(c) + ')\'>📈 Graphe</button> ' +
            '<button class="ghost" style="color:#be123c;font-size:11px;" onclick="deleteQcControl(' + c.id + ')">✕</button>' +
          '</td>'
        );
        if (active) tr.style.background = 'var(--teal-50, #f0fdfa)';
        return tr;
      }));
    }

    async function selectQcControl(control, scroll) {
      _qcSelectedControl = control;
      $('qcSelectedControlId').value = control.id;
      $('qcChartTitle').textContent = control.analyte + ' — ' + control.level + ' (' + (control.unit || '') + ')';
      $('qcDate').value = new Date().toISOString().slice(0, 10);
      $('qcChartPanel').style.display = '';
      $('qcEmptyPanel').style.display = 'none';

      const results = await api('/api/v1/qc/controls/' + control.id + '/results', { headers: headers(false) });
      $('qcChartContainer').innerHTML = results.length
        ? _ljSvg(control, results)
        : '<p style="color:var(--muted);font-size:13px;text-align:center;">Aucune mesure encore enregistrée.</p>';

      // Alert banner for last result
      const last = results[results.length - 1];
      const alertDiv = $('qcResultsAlert');
      const REJECT_RULES = ['1-3s','2-2s','R-4s','4-1s','10x'];
      if (last && last.violations && last.violations.length > 0) {
        const v = last.violations;
        const isReject = v.some(function(x){return REJECT_RULES.includes(x);});
        alertDiv.innerHTML = isReject
          ? '<div style="background:#fef2f2;border-left:4px solid #dc2626;padding:8px 12px;border-radius:4px;font-size:13px;">⛔ <strong>Rejet Westgard</strong> — règle(s) ' + v.join(', ') + ' violée(s) sur la dernière mesure.</div>'
          : '<div style="background:#fffbeb;border-left:4px solid #f59e0b;padding:8px 12px;border-radius:4px;font-size:13px;">⚠️ <strong>Avertissement 1-2s</strong> — surveiller la dérive analytique.</div>';
      } else {
        alertDiv.innerHTML = '';
      }

      // Results table (most recent first)
      setRows('qcResultsTable', [...results].reverse().map(function(r) {
        const z = ((r.value - control.target_mean) / control.target_sd).toFixed(2);
        const v = r.violations || [];
        const isReject = v.some(function(x){return REJECT_RULES.includes(x);});
        const badge = isReject
          ? '<span style="color:#be123c;font-weight:600;">⛔ ' + v.join(' ') + '</span>'
          : v.includes('1-2s')
            ? '<span style="color:#b45309;">⚠️ 1-2s</span>'
            : '<span style="color:#16a34a;">✅ OK</span>';
        return row(
          '<td>' + r.measured_at + '</td>' +
          '<td><strong>' + r.value + '</strong></td>' +
          '<td style="font-family:monospace;color:' + (Math.abs(Number(z)) > 2 ? '#b45309' : 'inherit') + ';">' + z + '</td>' +
          '<td>' + badge + '</td>' +
          '<td style="color:var(--muted);">' + security.escapeHtml(r.operator || '—') + '</td>'
        );
      }));

      if (scroll !== false) $('qcChartPanel').scrollIntoView({ behavior: 'smooth', block: 'start' });
      await loadQc();
    }

    async function createQcControl(btn) {
      setLoading(btn, true);
      try {
        const analyte = $('qcAnalyte').value.trim();
        const sd = Number($('qcSd').value);
        if (!analyte) throw new Error('Analyte obligatoire');
        if (!sd || sd <= 0) throw new Error('SD doit être > 0');
        await api('/api/v1/qc/controls', {
          method: 'POST', headers: headers(),
          body: JSON.stringify({
            analyte: analyte,
            level:   $('qcLevel').value.trim() || 'Niveau 1',
            unit:    $('qcUnit').value.trim(),
            target_mean: Number($('qcMean').value),
            target_sd:   sd,
          })
        });
        showToast('Contrôle QC créé', 'success');
        ['qcAnalyte','qcMean','qcSd','qcUnit'].forEach(function(id){ $(id).value = ''; });
        $('qcLevel').value = 'Niveau 1';
        await loadQc();
      } catch(e) {
        showToast(e.message || 'Erreur création contrôle', 'error');
      } finally {
        setLoading(btn, false);
      }
    }

    async function addQcResult(btn) {
      setLoading(btn, true);
      try {
        const id = Number($('qcSelectedControlId').value);
        const value = $('qcValue').value;
        const date  = $('qcDate').value;
        if (!id)    throw new Error('Aucun contrôle sélectionné');
        if (value === '') throw new Error('Valeur obligatoire');
        if (!date)  throw new Error('Date obligatoire');
        const result = await api('/api/v1/qc/results', {
          method: 'POST', headers: headers(),
          body: JSON.stringify({
            control_id: id,
            value: Number(value),
            measured_at: date,
            operator: $('qcOperator').value.trim() || null,
          })
        });
        $('qcValue').value = '';
        const v = result.violations || [];
        const REJECT_RULES = ['1-3s','2-2s','R-4s','4-1s','10x'];
        const isReject = v.some(function(x){return REJECT_RULES.includes(x);});
        if (isReject)         showToast('⛔ Rejet Westgard : ' + v.join(', '), 'error');
        else if (v.includes('1-2s')) showToast('⚠️ Avertissement 1-2s — surveiller la dérive', 'warn');
        else                  showToast('Mesure QC enregistrée ✅', 'success');
        if (_qcSelectedControl) await selectQcControl(_qcSelectedControl, false);
      } catch(e) {
        showToast(e.message || 'Erreur saisie mesure', 'error');
      } finally {
        setLoading(btn, false);
      }
    }

    async function deleteQcControl(id) {
      if (!confirm('Désactiver ce contrôle QC ? Les mesures existantes sont conservées.')) return;
      try {
        await api('/api/v1/qc/controls/' + id, { method: 'DELETE', headers: headers() });
        if (_qcSelectedControl && _qcSelectedControl.id === id) {
          _qcSelectedControl = null;
          $('qcChartPanel').style.display = 'none';
          $('qcEmptyPanel').style.display = '';
        }
        showToast('Contrôle désactivé', 'success');
        await loadQc();
      } catch(e) {
        showToast(e.message || 'Erreur désactivation', 'error');
      }
    }

    // ── Fin QC ───────────────────────────────────────────────────────────────

    function _expiryDays(dateStr) {
      if (!dateStr) return null;
      const d = new Date(dateStr + 'T00:00:00');
      const now = new Date(); now.setHours(0, 0, 0, 0);
      return Math.round((d - now) / 86400000);
    }
    function _expiryBadge(dateStr) {
      if (!dateStr) return '<span style="color:var(--muted);font-size:11px;">—</span>';
      const d = new Date(dateStr + 'T00:00:00');
      const days = _expiryDays(dateStr);
      const fmt = d.toLocaleDateString('fr-FR');
      if (days < 0)   return '<span style="color:#be123c;font-weight:600;font-size:12px;">⚠️ Périmé</span>';
      if (days <= 30) return '<span style="color:#b45309;font-size:12px;">⏳ ' + fmt + ' <small>(' + days + 'j)</small></span>';
      return '<span style="font-size:12px;">' + fmt + '</span>';
    }
    async function loadReagents() {
      const data = await api("/api/v1/reagents", { headers: headers(false) });
      setRows("reagentsTable", data.items.map((r) => {
        const isLow = r.alert_threshold > 0 && r.current_stock <= r.alert_threshold;
        const ed = _expiryDays(r.expiry_date);
        const tr = row(
          `<td data-label="ID">${r.id}</td>` +
          `<td data-label="Nom"><strong>${security.escapeHtml(r.name)}</strong></td>` +
          `<td data-label="Catégorie">${security.escapeHtml(r.category || '—')}</td>` +
          `<td data-label="Lot" style="font-size:11px;color:var(--muted);">${security.escapeHtml(r.lot_number || '—')}</td>` +
          `<td data-label="Péremption">${_expiryBadge(r.expiry_date)}</td>` +
          `<td data-label="Stock">${r.current_stock} <span style="font-size:11px;color:var(--muted);">${security.escapeHtml(r.unit || '')}</span></td>` +
          `<td data-label="Seuil">${r.alert_threshold}</td>` +
          `<td data-label="Action" style="white-space:nowrap;">` +
            `<button class="ghost" onclick='editReagent(${JSON.stringify(r)})'>Éditer</button>` +
          `</td>`
        );
        if (r.current_stock === 0 || (ed !== null && ed < 0)) tr.classList.add('row-critical');
        else if (isLow || (ed !== null && ed <= 30))          tr.classList.add('row-warning');
        return tr;
      }));
    }
    async function createReagent(btn) {
      return errorHandler.safeExecute(async () => {
        setLoading(btn, true);
        
        // Validate inputs
        const fields = {
          reagentName: { required: true },
          reagentCategory: { required: false },
          reagentStock: { required: true, numeric: true },
          reagentThreshold: { required: true, numeric: true }
        };
        
        let hasErrors = false;
        Object.entries(fields).forEach(([fieldId, rules]) => {
          const field = $(fieldId);
          const errors = validator.validateField(field, rules);
          validator.showFieldErrors(field, errors);
          if (errors.length > 0) hasErrors = true;
        });
        
        if (hasErrors) {
          throw new Error('Veuillez corriger les erreurs dans le formulaire');
        }
        
        const body = {
          name: security.sanitize($("reagentName").value),
          category: security.sanitize($("reagentCategory").value) || null,
          unit: security.sanitize($("reagentUnit").value),
          current_stock: Number(security.sanitizeNumber($("reagentStock").value)),
          alert_threshold: Number(security.sanitizeNumber($("reagentThreshold").value)),
          lot_number: security.sanitize($("reagentLot").value) || null,
          supplier: security.sanitize($("reagentSupplier").value) || null,
          expiry_date: $("reagentExpiry").value || null,
        };
        
        await perfMonitor.measureAsync('createReagent', () =>
          api("/api/v1/reagents", { method: "POST", headers: headers(), body: JSON.stringify(body) })
        );
        
        showToast("Réactif créé avec succès", "success");
        
        // Clear form
        ["reagentName", "reagentCategory", "reagentStock", "reagentThreshold", "reagentLot", "reagentSupplier", "reagentExpiry"].forEach(id => {
          const field = $(id);
          field.value = "";
          field.classList.remove('success-input', 'error-input');
          const errorDiv = field.parentNode.querySelector('.error-message');
          if (errorDiv) errorDiv.remove();
        });
        
        await loadReagents();
      }, 'createReagent').finally(() => setLoading(btn, false));
    }
    // ── Édition / réapprovisionnement réactifs ─────────────────────────────
    function editReagent(r) {
      $('reagentEditId').value = r.id;
      $('reagentEditName').textContent = r.name;
      $('editReagentName').value = r.name;
      $('editReagentCategory').value = r.category || '';
      $('editReagentUnit').value = r.unit || 'unit';
      $('editReagentStock').value = r.current_stock;
      $('editReagentThreshold').value = r.alert_threshold;
      $('editReagentLot').value = r.lot_number || '';
      $('editReagentSupplier').value = r.supplier || '';
      $('editReagentExpiry').value = r.expiry_date || '';
      $('restockQty').value = '';
      const panel = $('reagentEditPanel');
      panel.style.display = '';
      panel.scrollIntoView({ behavior: 'smooth', block: 'center' });
    }

    function closeReagentEdit() {
      $('reagentEditPanel').style.display = 'none';
    }

    async function saveReagent(btn) {
      setLoading(btn, true);
      try {
        const id = $('reagentEditId').value;
        const payload = {
          name: $('editReagentName').value.trim(),
          category: $('editReagentCategory').value.trim() || null,
          unit: $('editReagentUnit').value.trim() || 'unit',
          current_stock: Number($('editReagentStock').value),
          alert_threshold: Number($('editReagentThreshold').value),
          lot_number: $('editReagentLot').value.trim() || null,
          supplier: $('editReagentSupplier').value.trim() || null,
          expiry_date: $('editReagentExpiry').value || null,
        };
        if (!payload.name) throw new Error('Nom obligatoire');
        await api(`/api/v1/reagents/${id}`, {
          method: 'PUT', headers: headers(), body: JSON.stringify(payload),
        });
        showToast('Réactif mis à jour', 'success');
        closeReagentEdit();
        await loadReagents();
      } catch (e) {
        showToast(e.message || 'Erreur enregistrement', 'error');
      } finally {
        setLoading(btn, false);
      }
    }

    async function restockReagent(btn) {
      setLoading(btn, true);
      try {
        const id = $('reagentEditId').value;
        const qty = Number($('restockQty').value);
        if (!qty || qty <= 0) throw new Error('Quantité invalide (doit être > 0)');
        const newStock = Number($('editReagentStock').value) + qty;
        const payload = {
          name: $('editReagentName').value.trim(),
          category: $('editReagentCategory').value.trim() || null,
          unit: $('editReagentUnit').value.trim() || 'unit',
          current_stock: newStock,
          alert_threshold: Number($('editReagentThreshold').value),
          lot_number: $('editReagentLot').value.trim() || null,
          supplier: $('editReagentSupplier').value.trim() || null,
          expiry_date: $('editReagentExpiry').value || null,
        };
        await api(`/api/v1/reagents/${id}`, {
          method: 'PUT', headers: headers(), body: JSON.stringify(payload),
        });
        $('editReagentStock').value = newStock;
        $('restockQty').value = '';
        showToast(`Réapprovisionné +${qty} → stock: ${newStock}`, 'success');
        await loadReagents();
      } catch (e) {
        showToast(e.message || 'Erreur réapprovisionnement', 'error');
      } finally {
        setLoading(btn, false);
      }
    }

    async function openPdf() {
      try {
        const response = await fetch(`/api/v1/reports/results/${$("reportResultId").value}/pdf`, { headers: headers(false) });
        if (!response.ok) throw new Error("PDF non disponible");
        const blob = await response.blob();
        window.open(URL.createObjectURL(blob), "_blank");
        showToast("PDF ouvert dans un nouvel onglet", "success");
      } catch (e) {
        showToast("Erreur lors de l'ouverture du PDF", "error");
      }
    }
    async function signPdf(btn) {
      setLoading(btn, true);
      try {
        await api(`/api/v1/reports/results/${$("reportResultId").value}/sign`, { method: "POST", headers: headers(), body: JSON.stringify({ signature_meaning: "Validation par l'officier de garde." }) });
        showToast("Résultat signé et validé avec succès", "success");
      } catch (e) {
        showToast("Erreur lors de la signature", "error");
      } finally {
        setLoading(btn, false);
      }
    }
    function downloadEpiCsv() { window.open("/api/v1/reports/epidemiology-export.csv?days=30", "_blank"); }
    token = storage.getItem("ruggylab_token") || "";
    if (token) {
      boot();
    } else {
      logout();
    }
    
    // Initialize keyboard shortcuts
    keyboard.init();
    
    // Initialize service worker for offline functionality
    if ('serviceWorker' in navigator) {
      navigator.serviceWorker.register('/static/sw.js')
        .then(registration => {
          console.log('Service Worker registered:', registration);
        })
        .catch(error => {
          console.log('Service Worker registration failed:', error);
        });
      
      // Listen for messages from service worker
      navigator.serviceWorker.addEventListener('message', event => {
        if (event.data.type === 'SYNC_COMPLETE') {
          showToast('Synchronisation terminée', 'success');
          refreshCurrent(true);
        }
      });
    }
    
    // Offline detection
    const offlineDetector = {
      init: () => {
        window.addEventListener('online', () => {
          showToast('Connexion rétablie', 'success');
          refreshCurrent(true);
        });
        
        window.addEventListener('offline', () => {
          showToast('Hors ligne - Données en cache uniquement', 'warning');
        });
        
        // Update connection status
        offlineDetector.updateStatus();
        setInterval(() => offlineDetector.updateStatus(), 30000);
      },
      
      updateStatus: () => {
        const status = navigator.onLine ? 'En ligne' : 'Hors ligne';
        const userStatus = $('userStatus');
        if (userStatus) {
          const currentText = userStatus.textContent;
          userStatus.textContent = `${currentText.split(' - ')[0]} - ${status}`;
        }
      }
    };
    
    offlineDetector.init();
    
    // AI Engine - RuggyLab Intelligence
    const ruggyAI = {
      models: new Map(),
      isInitialized: false,
      
      async init() {
        try {
          // Charger les modèles IA
          await this.loadModels();
          
          // Initialiser les pipelines
          this.setupPipelines();
          
          this.isInitialized = true;
          showToast('Moteur IA initialisé avec succès', 'success');
        } catch (error) {
          errorHandler.handle(error, 'AI initialization');
        }
      },
      
      async loadModels() {
        try {
          // Modèle de classification d'images (MobileNet pré-entraîné)
          console.log('Chargement modèle Computer Vision...');
          const visionModel = await mobilenet.load();
          this.models.set('vision', visionModel);
          
          // Modèle personnalisé pour détection paludisme (simulation)
          const malariaModel = await this.createMalariaModel();
          this.models.set('malaria', malariaModel);
          
          // Modèle de détection d'anomalies
          const anomalyModel = await this.createAnomalyModel();
          this.models.set('anomaly', anomalyModel);
          
        } catch (error) {
          throw new Error(`Erreur chargement modèles IA: ${error.message}`);
        }
      },
      
      async createMalariaModel() {
        // Créer un modèle simple pour détection paludisme
        const model = tf.sequential({
          layers: [
            tf.layers.dense({inputShape: [224*224*3], units: 128, activation: 'relu'}),
            tf.layers.dropout({rate: 0.2}),
            tf.layers.dense({units: 64, activation: 'relu'}),
            tf.layers.dense({units: 2, activation: 'softmax'}) // Parasité vs Non parasité
          ]
        });
        
        model.compile({
          optimizer: 'adam',
          loss: 'categoricalCrossentropy',
          metrics: ['accuracy']
        });
        
        return model;
      },
      
      async createAnomalyModel() {
        // Modèle pour détecter les anomalies dans les résultats de laboratoire
        const model = tf.sequential({
          layers: [
            tf.layers.dense({inputShape: [10], units: 32, activation: 'relu'}),
            tf.layers.dense({units: 16, activation: 'relu'}),
            tf.layers.dense({units: 1, activation: 'sigmoid'}) // Anomaly vs Normal
          ]
        });
        
        model.compile({
          optimizer: 'adam',
          loss: 'binaryCrossentropy',
          metrics: ['accuracy']
        });
        
        return model;
      },
      
      setupPipelines() {
        // Configurer les pipelines de traitement IA
        this.pipelines = {
          imageAnalysis: new ImageAnalysisPipeline(),
          resultAnalysis: new ResultAnalysisPipeline(),
          predictiveAnalytics: new PredictiveAnalyticsPipeline()
        };
      },
      
      // Computer Vision - Analyse d'images médicales
      async analyzeImage(imageElement, type = 'general') {
        if (!this.isInitialized) {
          throw new Error('Moteur IA non initialisé');
        }
        
        try {
          const predictions = await this.pipelines.imageAnalysis.process(imageElement, type);
          return this.explainPredictions(predictions, type);
        } catch (error) {
          errorHandler.handle(error, 'image analysis');
          throw error;
        }
      },
      
      // Anomaly Detection - Résultats de laboratoire
      async detectAnomalies(results) {
        if (!this.isInitialized) {
          throw new Error('Moteur IA non initialisé');
        }
        
        try {
          const anomalies = await this.pipelines.resultAnalysis.detectAnomalies(results);
          return this.formatAnomalyReport(anomalies);
        } catch (error) {
          errorHandler.handle(error, 'anomaly detection');
          throw error;
        }
      },
      
      // Predictive Analytics - Prédictions diverses
      async predict(data, type) {
        if (!this.isInitialized) {
          throw new Error('Moteur IA non initialisé');
        }
        
        try {
          return await this.pipelines.predictiveAnalytics.predict(data, type);
        } catch (error) {
          errorHandler.handle(error, 'prediction');
          throw error;
        }
      },
      
      explainPredictions(predictions, type) {
        // Rendre les prédictions IA explicables
        return {
          predictions,
          confidence: this.calculateConfidence(predictions),
          explanation: this.generateExplanation(predictions, type),
          recommendations: this.generateRecommendations(predictions, type)
        };
      },
      
      calculateConfidence(predictions) {
        if (!predictions || predictions.length === 0) return 0;
        const maxProb = Math.max(...predictions.map(p => p.probability));
        return Math.round(maxProb * 100);
      },
      
      generateExplanation(predictions, type) {
        const explanations = {
          malaria: {
            positive: 'Parasites de Plasmodium détectés dans les globules rouges',
            negative: 'Aucun parasite de Plasmodium détecté',
            uncertain: 'Analyse incertaine - recommander nouvel examen'
          },
          general: {
            high: 'Forte confiance dans la classification',
            medium: 'Confiance modérée - vérification recommandée',
            low: 'Faible confiance - analyse complémentaire nécessaire'
          }
        };
        
        const topPrediction = predictions[0];
        const confidence = this.calculateConfidence(predictions);
        
        if (confidence > 80) return explanations[type]?.positive || explanations.general.high;
        if (confidence > 60) return explanations[type]?.negative || explanations.general.medium;
        return explanations[type]?.uncertain || explanations.general.low;
      },
      
      generateRecommendations(predictions, type) {
        const recommendations = [];
        const confidence = this.calculateConfidence(predictions);
        
        if (type === 'malaria') {
          const topPrediction = predictions[0];
          if (topPrediction.className.includes('parasite') && confidence > 70) {
            recommendations.push('Confirmer avec test rapide antigénique');
            recommendations.push('Initier traitement antipaludique si cliniquement justifié');
          } else if (confidence < 60) {
            recommendations.push('Répéter l\'examen avec nouveau frottis');
            recommendations.push('Considérer test de diagnostic rapide');
          } else {
            recommendations.push('Surveillance clinique recommandée');
          }
        }
        
        if (confidence < 70) {
          recommendations.push('Validation par biologiste senior recommandée');
        }
        
        return recommendations;
      },
      
      formatAnomalyReport(anomalies) {
        return {
          hasAnomalies: anomalies.length > 0,
          criticalAnomalies: anomalies.filter(a => a.severity === 'critical'),
          warningAnomalies: anomalies.filter(a => a.severity === 'warning'),
          summary: this.generateAnomalySummary(anomalies),
          recommendations: this.generateAnomalyRecommendations(anomalies)
        };
      },
      
      generateAnomalySummary(anomalies) {
        const critical = anomalies.filter(a => a.severity === 'critical').length;
        const warnings = anomalies.filter(a => a.severity === 'warning').length;
        
        if (critical > 0) {
          return `${critical} anomalie(s) critique(s) détectée(s) - Action immédiate requise`;
        } else if (warnings > 0) {
          return `${warnings} anomalie(s) mineure(s) détectée(s) - Surveillance recommandée`;
        }
        return 'Aucune anomalie détectée';
      },
      
      generateAnomalyRecommendations(anomalies) {
        const recommendations = [];
        
        anomalies.forEach(anomaly => {
          switch (anomaly.type) {
            case 'critical_value':
              recommendations.push('Répéter l\'analyse immédiatement');
              recommendations.push('Notifier le médecin prescripteur');
              break;
            case 'trend_anomaly':
              recommendations.push('Analyser l\'évolution sur 3 derniers résultats');
              recommendations.push('Considérer un contrôle de qualité');
              break;
            case 'out_of_range':
              recommendations.push('Vérifier calibration équipement');
              recommendations.push('Confirmer identité patient');
              break;
          }
        });
        
        return [...new Set(recommendations)]; // Dédupliquer
      }
    };
    
    // Pipeline d'analyse d'images
    class ImageAnalysisPipeline {
      async process(imageElement, type) {
        const model = ruggyAI.models.get('vision');
        const predictions = await model.classify(imageElement);
        
        // Post-traitement selon le type d'analyse
        if (type === 'malaria') {
          return this.processMalariaAnalysis(predictions);
        }
        
        return predictions;
      }
      
      processMalariaAnalysis(predictions) {
        // Filtrer et adapter les prédictions pour le paludisme
        const malariaPredictions = predictions.map(p => ({
          className: this.mapToMalariaClass(p.className),
          probability: p.probability
        }));
        
        return malariaPredictions.sort((a, b) => b.probability - a.probability);
      }
      
      mapToMalariaClass(originalClass) {
        // Mapper les classes MobileNet vers classes paludisme
        const malariaMapping = {
          'cell': 'cellules_saines',
          'microscope': 'parasites_detectes',
          'blood': 'echantillon_sang',
          'medicine': 'traitement_requis'
        };
        
        for (const [key, value] of Object.entries(malariaMapping)) {
          if (originalClass.toLowerCase().includes(key)) {
            return value;
          }
        }
        
        return originalClass;
      }
    }
    
    // Pipeline d'analyse de résultats
    class ResultAnalysisPipeline {
      async detectAnomalies(results) {
        const anomalies = [];
        
        // Détection valeurs critiques
        results.forEach(result => {
          if (this.isCriticalValue(result)) {
            anomalies.push({
              type: 'critical_value',
              severity: 'critical',
              parameter: result.parameter,
              value: result.value,
              expected: this.getExpectedRange(result.parameter)
            });
          }
          
          if (this.isOutOfRange(result)) {
            anomalies.push({
              type: 'out_of_range',
              severity: 'warning',
              parameter: result.parameter,
              value: result.value,
              expected: this.getExpectedRange(result.parameter)
            });
          }
        });
        
        // Détection tendances anormales
        const trendAnomalies = this.detectTrendAnomalies(results);
        anomalies.push(...trendAnomalies);
        
        return anomalies;
      }
      
      isCriticalValue(result) {
        const criticalRanges = {
          'WBC': { min: 0.5, max: 50 }, // Globules blancs
          'RBC': { min: 2, max: 8 },    // Globules rouges
          'HGB': { min: 50, max: 200 },  // Hémoglobine
          'PLT': { min: 20, max: 1000 }  // Plaquettes
        };
        
        const range = criticalRanges[result.parameter];
        if (!range) return false;
        
        return result.value < range.min || result.value > range.max;
      }
      
      isOutOfRange(result) {
        const normalRanges = {
          'WBC': { min: 4, max: 11 },
          'RBC': { min: 4.2, max: 5.4 },
          'HGB': { min: 120, max: 160 },
          'PLT': { min: 150, max: 450 }
        };
        
        const range = normalRanges[result.parameter];
        if (!range) return false;
        
        return result.value < range.min || result.value > range.max;
      }
      
      getExpectedRange(parameter) {
        const ranges = {
          'WBC': '4.0 - 11.0 x10⁹/L',
          'RBC': '4.2 - 5.4 x10¹²/L',
          'HGB': '120 - 160 g/L',
          'PLT': '150 - 450 x10⁹/L'
        };
        
        return ranges[parameter] || 'Non défini';
      }
      
      detectTrendAnomalies(results) {
        // Simulation de détection de tendances anormales
        // En pratique, utiliserait les données historiques
        const anomalies = [];
        
        // Exemple: détecter variations > 50% entre analyses
        if (results.length >= 2) {
          const latest = results[results.length - 1];
          const previous = results[results.length - 2];
          
          if (latest.parameter === previous.parameter) {
            const variation = Math.abs((latest.value - previous.value) / previous.value);
            
            if (variation > 0.5) {
              anomalies.push({
                type: 'trend_anomaly',
                severity: 'warning',
                parameter: latest.parameter,
                variation: Math.round(variation * 100)
              });
            }
          }
        }
        
        return anomalies;
      }
    }
    
    // Pipeline d'analyse prédictive
    class PredictiveAnalyticsPipeline {
      async predict(data, type) {
        switch (type) {
          case 'inventory':
            return this.predictInventoryNeeds(data);
          case 'workload':
            return this.predictWorkload(data);
          case 'quality':
            return this.predictQualityIssues(data);
          default:
            throw new Error(`Type de prédiction non supporté: ${type}`);
        }
      }
      
      predictInventoryNeeds(currentStock) {
        // Prédire les besoins de stock pour les 30 prochains jours
        const predictions = {};
        
        Object.entries(currentStock).forEach(([item, stock]) => {
          const dailyUsage = this.estimateDailyUsage(item);
          const daysUntilEmpty = Math.floor(stock / dailyUsage);
          
          predictions[item] = {
            currentStock: stock,
            dailyUsage: dailyUsage,
            daysUntilEmpty: daysUntilEmpty,
            recommendedOrder: this.calculateRecommendedOrder(stock, dailyUsage),
            urgency: this.calculateUrgency(daysUntilEmpty),
            predictionDate: new Date(Date.now() + (daysUntilEmpty * 24 * 60 * 60 * 1000))
          };
        });
        
        return predictions;
      }
      
      predictWorkload(historicalData) {
        // Prédire la charge de travail basée sur les tendances
        const dayOfWeek = new Date().getDay();
        const seasonalFactor = this.getSeasonalFactor();
        
        const avgDailySamples = historicalData.reduce((sum, day) => sum + day.samples, 0) / historicalData.length;
        
        const predicted = Math.round(avgDailySamples * seasonalFactor * this.getDayFactor(dayOfWeek));
        
        return {
          predictedSamples: predicted,
          confidence: 75,
          factors: {
            seasonal: seasonalFactor,
            dayOfWeek: dayOfWeek,
            trend: this.calculateTrend(historicalData)
          },
          recommendations: this.generateWorkloadRecommendations(predicted)
        };
      }
      
      predictQualityIssues(qualityData) {
        // Prédire les problèmes de qualité potentiels
        const riskFactors = {
          equipmentAge: qualityData.equipmentAge || 0,
          maintenanceScore: qualityData.maintenanceScore || 100,
          operatorExperience: qualityData.operatorExperience || 100,
          environmentalFactors: qualityData.environmentalFactors || 100
        };
        
        const riskScore = this.calculateQualityRisk(riskFactors);
        
        return {
          riskScore: riskScore,
          riskLevel: this.getRiskLevel(riskScore),
          contributingFactors: this.identifyRiskFactors(riskFactors),
          recommendations: this.generateQualityRecommendations(riskScore, riskFactors)
        };
      }
      
      // Méthodes utilitaires pour les prédictions
      estimateDailyUsage(item) {
        const usagePatterns = {
          'EDTA': 15,    // Tubes par jour
          'Citrate': 8,
          'Heparine': 12,
          'ReactifNFS': 25,
          'LameMicroscope': 30
        };
        
        return usagePatterns[item] || 10;
      }
      
      calculateRecommendedOrder(currentStock, dailyUsage) {
        const safetyStock = dailyUsage * 7; // 7 jours de stock de sécurité
        const orderQuantity = Math.max(0, safetyStock - currentStock + (dailyUsage * 30));
        
        return Math.ceil(orderQuantity);
      }
      
      calculateUrgency(daysUntilEmpty) {
        if (daysUntilEmpty <= 3) return 'critical';
        if (daysUntilEmpty <= 7) return 'high';
        if (daysUntilEmpty <= 14) return 'medium';
        return 'low';
      }
      
      getSeasonalFactor() {
        const month = new Date().getMonth();
        const seasonalFactors = [0.9, 0.8, 0.9, 1.0, 1.1, 1.2, 1.3, 1.2, 1.1, 1.0, 0.9, 0.9];
        return seasonalFactors[month];
      }
      
      getDayFactor(dayOfWeek) {
        const dayFactors = [0.7, 1.0, 1.2, 1.1, 1.0, 0.5, 0.3]; // Dimanche=0
        return dayFactors[dayOfWeek];
      }
      
      calculateTrend(historicalData) {
        if (historicalData.length < 2) return 'stable';
        
        const recent = historicalData.slice(-7);
        const older = historicalData.slice(-14, -7);
        
        const recentAvg = recent.reduce((sum, day) => sum + day.samples, 0) / recent.length;
        const olderAvg = older.reduce((sum, day) => sum + day.samples, 0) / older.length;
        
        const change = (recentAvg - olderAvg) / olderAvg;
        
        if (change > 0.1) return 'increasing';
        if (change < -0.1) return 'decreasing';
        return 'stable';
      }
      
      generateWorkloadRecommendations(predictedSamples) {
        const recommendations = [];
        
        if (predictedSamples > 100) {
          recommendations.push('Prévoir personnel supplémentaire');
          recommendations.push('Vérifier disponibilité équipements');
        } else if (predictedSamples < 50) {
          recommendations.push('Optimiser planning personnel');
          recommendations.push('Planifier maintenance équipements');
        }
        
        return recommendations;
      }
      
      calculateQualityRisk(riskFactors) {
        const weights = {
          equipmentAge: 0.3,
          maintenanceScore: 0.3,
          operatorExperience: 0.2,
          environmentalFactors: 0.2
        };
        
        let riskScore = 0;
        
        // Équipement ancien augmente le risque
        riskScore += (riskFactors.equipmentAge / 10) * weights.equipmentAge;
        
        // Score de maintenance bas augmente le risque
        riskScore += ((100 - riskFactors.maintenanceScore) / 100) * weights.maintenanceScore;
        
        // Expérience opérateur faible augmente le risque
        riskScore += ((100 - riskFactors.operatorExperience) / 100) * weights.operatorExperience;
        
        // Facteurs environnementaux
        riskScore += ((100 - riskFactors.environmentalFactors) / 100) * weights.environmentalFactors;
        
        return Math.min(100, Math.round(riskScore * 100));
      }
      
      getRiskLevel(riskScore) {
        if (riskScore >= 80) return 'critical';
        if (riskScore >= 60) return 'high';
        if (riskScore >= 40) return 'medium';
        return 'low';
      }
      
      identifyRiskFactors(riskFactors) {
        const factors = [];
        
        if (riskFactors.equipmentAge > 5) {
          factors.push('Équipement ancien (>5 ans)');
        }
        if (riskFactors.maintenanceScore < 70) {
          factors.push('Maintenance insuffisante');
        }
        if (riskFactors.operatorExperience < 60) {
          factors.push('Expérience opérateur limitée');
        }
        if (riskFactors.environmentalFactors < 70) {
          factors.push('Conditions environnementales dégradées');
        }
        
        return factors;
      }
      
      generateQualityRecommendations(riskScore, riskFactors) {
        const recommendations = [];
        
        if (riskScore >= 60) {
          recommendations.push('Augmenter fréquence contrôles qualité');
          recommendations.push('Planner formation personnel');
        }
        
        if (riskFactors.equipmentAge > 5) {
          recommendations.push('Évaluer remplacement équipement');
        }
        
        if (riskFactors.maintenanceScore < 70) {
          recommendations.push('Programmer maintenance préventive');
        }
        
        if (riskFactors.operatorExperience < 60) {
          recommendations.push('Organiser session de formation');
        }
        
        return recommendations;
      }
    }
    
    // AI Training Interface Functions
    function initializeAIDataset() {
      try {
        const dataset = malariaDatasetCollector.initializeMalariaDataset();
        
        $('currentDatasetName').value = dataset.name;
        $('totalSamples').value = dataset.size;
        $('annotatedSamples').value = '0';
        
        showToast('Dataset IA initialisé avec succès', 'success');
        updateDatasetStats();
      } catch (error) {
        errorHandler.handle(error, 'AI dataset initialization');
      }
    }
    
    function previewTrainingImage(input) {
      const file = input.files[0];
      const preview = $('trainingImagePreview');
      
      if (file) {
        const reader = new FileReader();
        reader.onload = function(e) {
          preview.innerHTML = `
            <img id="trainingImageElement" src="${e.target.result}" style="max-width: 300px; max-height: 300px; border-radius: 8px; border: 1px solid var(--line);" />
            <div style="margin-top: 5px; font-size: 12px; color: var(--muted);">${file.name} (${(file.size / 1024).toFixed(1)} KB)</div>
          `;
        };
        reader.readAsDataURL(file);
      } else {
        preview.innerHTML = '';
      }
    }
    
    async function addTrainingSample() {
      const imageElement = $('trainingImageElement');
      const annotation = $('imageAnnotation').value;
      const notes = $('annotationNotes').value;
      
      if (!imageElement) {
        showToast('Veuillez d\'abord uploader une image', 'warning');
        return;
      }
      
      try {
        loadingStates.showLoadingOverlay('Ajout échantillon au dataset...');
        
        // Convertir l'image en base64
        const imageData = imageElement.src;
        
        // Ajouter l'échantillon
        const result = await malariaDatasetCollector.collectMicroscopeImage(imageData, annotation);
        
        if (result.success) {
          // Ajouter l'annotation détaillée
          if (notes) {
            malariaDatasetCollector.annotateDetailed(
              result.sample.id,
              annotation === 'positive' ? 1 : 0,
              100,
              notes
            );
          }
          
          // Mettre à jour l'interface
          $('totalSamples').value = malariaDatasetCollector.currentDataset.size;
          
          // Réinitialiser le formulaire
          $('trainingImage').value = '';
          $('trainingImagePreview').innerHTML = '';
          $('annotationNotes').value = '';
          
          updateDatasetStats();
          showToast('Échantillon ajouté avec succès', 'success');
        } else {
          showToast(`Erreur: ${result.reason}`, 'error');
        }
        
        loadingStates.hideLoadingOverlay();
      } catch (error) {
        errorHandler.handle(error, 'training sample addition');
        loadingStates.hideLoadingOverlay();
      }
    }
    
    function showDatasetStats() {
      try {
        const stats = malariaDatasetCollector.getDatasetStatistics();
        
        if (!stats) {
          showToast('Aucun dataset initialisé', 'warning');
          return;
        }
        
        const statsDiv = $('datasetStats');
        statsDiv.innerHTML = `
          <div style="display: grid; gap: 15px;">
            <div class="prediction-item">
              <span class="prediction-label">Total Échantillons</span>
              <span class="prediction-value">${stats.totalSamples}</span>
            </div>
            <div class="prediction-item">
              <span class="prediction-label">Positifs (Parasites)</span>
              <span class="prediction-value" style="color: var(--rose);">${stats.malariaSpecific.positive || 0}</span>
            </div>
            <div class="prediction-item">
              <span class="prediction-label">Négatifs (Sains)</span>
              <span class="prediction-value" style="color: var(--ok);">${stats.malariaSpecific.negative || 0}</span>
            </div>
            <div class="prediction-item">
              <span class="prediction-label">Non annotés</span>
              <span class="prediction-value" style="color: var(--muted);">${stats.malariaSpecific.unlabeled || 0}</span>
            </div>
            <div class="prediction-item">
              <span class="prediction-label">Taux d'annotation</span>
              <span class="prediction-value">${stats.annotationRate.toFixed(1)}%</span>
            </div>
            <div class="prediction-item">
              <span class="prediction-label">Créé le</span>
              <span class="prediction-value">${new Date(stats.created).toLocaleDateString('fr-FR')}</span>
            </div>
          </div>
        `;
      } catch (error) {
        errorHandler.handle(error, 'dataset stats display');
      }
    }
    
    function updateDatasetStats() {
      showDatasetStats();
    }
    
    function validateAnnotations() {
      try {
        const validation = malariaDatasetCollector.validateAnnotations();
        
        if (validation.valid) {
          showToast('✅ Toutes les annotations sont valides', 'success');
        } else {
          const issuesDiv = $('datasetStats');
          issuesDiv.innerHTML = `
            <div style="color: var(--rose);">
              <h4>❌ Problèmes détectés (${validation.issues.length})</h4>
              <ul style="margin: 10px 0; padding-left: 20px;">
                ${validation.issues.slice(0, 10).map(issue => `<li>${issue}</li>`).join('')}
                ${validation.issues.length > 10 ? `<li>... et ${validation.issues.length - 10} autres</li>` : ''}
              </ul>
              <div style="margin-top: 10px;">
                <strong>Échantillons annotés:</strong> ${validation.annotatedSamples} / ${validation.totalSamples}
              </div>
            </div>
          `;
          showToast('Problèmes détectés dans les annotations', 'warning');
        }
      } catch (error) {
        errorHandler.handle(error, 'annotation validation');
      }
    }
    
    function exportDataset() {
      try {
        const exportData = malariaDatasetCollector.exportForTraining();
        
        // Créer un blob et télécharger
        const blob = new Blob([exportData], { type: 'application/json' });
        const url = URL.createObjectURL(blob);
        const a = document.createElement('a');
        a.href = url;
        a.download = `malaria_dataset_${new Date().toISOString().split('T')[0]}.json`;
        document.body.appendChild(a);
        a.click();
        document.body.removeChild(a);
        URL.revokeObjectURL(url);
        
        showToast('Dataset exporté avec succès', 'success');
      } catch (error) {
        errorHandler.handle(error, 'dataset export');
      }
    }
    
    // AI Interface Functions
    function previewMalariaImage(input) {
      const file = input.files[0];
      const preview = $('malariaPreview');
      
      if (file) {
        const reader = new FileReader();
        reader.onload = function(e) {
          preview.innerHTML = `
            <img id="malariaImagePreview" src="${e.target.result}" style="max-width: 200px; max-height: 200px; border-radius: 8px; border: 1px solid var(--line);" />
            <div style="margin-top: 5px; font-size: 12px; color: var(--muted);">${file.name}</div>
          `;
        };
        reader.readAsDataURL(file);
      } else {
        preview.innerHTML = '';
      }
    }
    
    async function analyzeMalariaWithAI() {
      if (!ruggyAI.isInitialized) {
        showToast('Moteur IA non initialisé', 'error');
        return;
      }
      
      const imagePreview = $('malariaImagePreview');
      if (!imagePreview) {
        showToast('Veuillez d\'abord uploader une image', 'warning');
        return;
      }
      
      try {
        loadingStates.showLoadingOverlay('Analyse IA en cours...');
        
        // Analyser l'image avec l'IA
        const results = await ruggyAI.analyzeImage(imagePreview, 'malaria');
        
        // Afficher les résultats
        displayAIResults(results);
        
        showToast('Analyse IA terminée', 'success');
        loadingStates.hideLoadingOverlay();
        
      } catch (error) {
        errorHandler.handle(error, 'malaria AI analysis');
        loadingStates.hideLoadingOverlay();
      }
    }
    
    function displayAIResults(results) {
      const resultsDiv = $('aiResults');
      
      const confidenceClass = results.confidence > 80 ? 'confidence-high' : 
                             results.confidence > 60 ? 'confidence-medium' : 'confidence-low';
      
      resultsDiv.innerHTML = `
        <div class="ai-results">
          <h4>🤖 Résultats Analyse IA</h4>
          
          <div class="ai-confidence">
            <span>Confiance:</span>
            <div class="confidence-bar">
              <div class="confidence-fill ${confidenceClass}" style="width: ${results.confidence}%"></div>
            </div>
            <span>${results.confidence}%</span>
          </div>
          
          <div class="ai-predictions">
            ${results.predictions.map(pred => `
              <div class="prediction-item">
                <span class="prediction-label">${pred.className}</span>
                <span class="prediction-value">${Math.round(pred.probability * 100)}%</span>
              </div>
            `).join('')}
          </div>
          
          <div class="ai-explanation">
            <strong>📋 Explication:</strong> ${results.explanation}
          </div>
          
          ${results.recommendations.length > 0 ? `
            <div class="ai-recommendations">
              <strong>💡 Recommandations:</strong>
              <ul>
                ${results.recommendations.map(rec => `<li>${rec}</li>`).join('')}
              </ul>
            </div>
          ` : ''}
        </div>
      `;
    }
    
    // ── analyzeResultsWithAI (stub appelant le backend) ─────────────────────────
    async function analyzeResultsWithAI() {
      showToast('Analyse IA: utilisez la vue Imagerie IA pour l\'analyse paludisme.', 'success');
      log('Analyse IA dédiée : vue Imagerie IA → Analyser IA avec un Result ID.\nPour l\'analyse NFS, les statuts critiques sont calculés automatiquement à la saisie du résultat.');
    }

    // ── Stock predictor / notifications CMU ────────────────────────────────────
    function addStockDrugLine(defaults = {}) {
      const div = document.createElement('div');
      div.className = 'panel';
      div.style.cssText = 'padding:10px;';
      div.innerHTML = `
        <div class="grid3" style="gap:6px;align-items:end;">
          <div><label>DCI</label><input data-stock-dci value="${defaults.dci_code || ''}" placeholder="ARTEMETHER-LUMEFANTRINE" /></div>
          <div><label>Stock actuel</label><input data-stock-current type="number" min="0" value="${defaults.current_stock ?? 80}" /></div>
          <div><label>CMM</label><input data-stock-cmm type="number" min="1" value="${defaults.cmm_units ?? 120}" /></div>
        </div>
        <div class="grid3" style="gap:6px;margin-top:6px;align-items:end;">
          <div><label>Catégorie</label><select data-stock-category>
            ${['ANTIMALARIAL','ANTIBIOTIC','ANALGESIC','ANTIDIABETIC','ANTIHYPERTENSIVE','RESPIRATORY','GENERAL'].map(c => `<option ${c === (defaults.disease_category || 'GENERAL') ? 'selected' : ''}>${c}</option>`).join('')}
          </select></div>
          <div><label>Coût unit. XOF</label><input data-stock-cost type="number" min="1" value="${defaults.unit_cost_xof || ''}" placeholder="opt." /></div>
          <div><button class="danger" style="width:100%;" onclick="this.closest('.panel').remove()">Supprimer</button></div>
        </div>
      `;
      $('stockDrugLines').appendChild(div);
    }

    function collectStockDrugLines() {
      const drugs = Array.from($('stockDrugLines').children).map(panel => {
        const dci = panel.querySelector('[data-stock-dci]')?.value?.trim();
        const current = panel.querySelector('[data-stock-current]')?.value;
        const cmm = panel.querySelector('[data-stock-cmm]')?.value;
        if (!dci || current === '' || cmm === '') return null;
        const line = {
          dci_code: dci,
          current_stock: Number(current),
          cmm_units: Number(cmm),
          disease_category: panel.querySelector('[data-stock-category]')?.value || 'GENERAL'
        };
        const cost = panel.querySelector('[data-stock-cost]')?.value;
        if (cost) line.unit_cost_xof = Number(cost);
        return line;
      }).filter(Boolean);
      if (!drugs.length) throw new Error('Ajoutez au moins un médicament à prédire.');
      return drugs;
    }

    function stockBasePayload() {
      return {
        drugs: collectStockDrugLines(),
        horizon_days: Number($('stockHorizon').value)
      };
    }

    async function predictInventoryNeeds(btn) {
      if (btn) setLoading(btn, true);
      try {
        const payload = {
          ...stockBasePayload(),
          include_fhir: $('stockIncludeFhir').value === 'true'
        };
        const data = await api('/stock/predict', {
          method: 'POST',
          headers: headers(),
          body: JSON.stringify(payload)
        });
        $('stockPredictionResult').textContent = JSON.stringify(data, null, 2);
        log(data);
        const n = data.drug_predictions?.length ?? 0;
        showToast(`Prédictions stocks : ${n} médicament(s) analysé(s)`, 'success');
      } catch (e) {
        $('stockPredictionResult').textContent = e.message || String(e);
        showToast('Erreur prédiction stock', 'error');
      } finally {
        if (btn) setLoading(btn, false);
      }
    }

    async function notifyStockAlerts(btn) {
      if (btn) setLoading(btn, true);
      try {
        const channel = $('stockChannel').value;
        const payload = {
          ...stockBasePayload(),
          channel,
          severity_filter: $('stockSeverity').value,
          facility_id: $('stockFacility').value || null,
          webhook_url: $('stockWebhook').value || null,
          email_to: $('stockEmails').value ? $('stockEmails').value.split(',').map(v => v.trim()).filter(Boolean) : null
        };
        const data = await api('/stock/notify', {
          method: 'POST',
          headers: headers(),
          body: JSON.stringify(payload)
        });
        $('stockPredictionResult').textContent = JSON.stringify(data, null, 2);
        showToast(`${data.notifications_sent ?? 0} notification(s) envoyée(s)`, 'success');
      } catch (e) {
        $('stockPredictionResult').textContent = e.message || String(e);
        showToast('Erreur notification stock', 'error');
      } finally {
        if (btn) setLoading(btn, false);
      }
    }

    function buildPrescriptionPayload() {
      const diagnoses = ($('rxDiagnoses').value || '')
        .split(',')
        .map(code => code.trim())
        .filter(Boolean)
        .map(code => ({ code }));
      const drugs = ($('rxDrugs').value || '')
        .split('\n')
        .map(line => line.split(',').map(part => part.trim()))
        .filter(parts => parts[0])
        .map(([dci, dose, freq, duration]) => ({
          dci: { code: dci },
          dose_mg: dose ? Number(dose) : null,
          frequency_per_day: freq ? Number(freq) : null,
          duration_days: duration ? Number(duration) : null,
          route: 'oral'
        }));
      if (!diagnoses.length) throw new Error('Ajoutez au moins un diagnostic CIM-10.');
      if (!drugs.length) throw new Error('Ajoutez au moins un médicament DCI.');
      return {
        diagnoses,
        drugs,
        patient: {
          age_years: Number($('rxAge').value || 0),
          sex: $('rxSex').value,
          weight_kg: $('rxWeight').value ? Number($('rxWeight').value) : null
        },
        prescriber_id: $('rxPrescriber').value || null,
        prescription_date: $('rxDate').value || null,
        qr_code_token: $('rxQrToken').value || null
      };
    }

    async function scanPrescription(btn) {
      setLoading(btn, true);
      try {
        const data = await api('/prescription/scan', {
          method: 'POST',
          headers: headers(),
          body: JSON.stringify(buildPrescriptionPayload())
        });
        $('rxResult').textContent = JSON.stringify(data, null, 2);
        showToast(`Ordonnance: ${data.status} (${Math.round((data.confidence_score || 0) * 100)}%)`, data.status === 'BLOCKED' ? 'warning' : 'success');
      } catch (e) {
        $('rxResult').textContent = e.message || String(e);
        showToast('Erreur scan ordonnance', 'error');
      } finally {
        setLoading(btn, false);
      }
    }

    async function openPrescriptionPdf(btn) {
      setLoading(btn, true);
      try {
        const response = await fetch('/api/v1/prescription/report', {
          method: 'POST',
          headers: headers(),
          body: JSON.stringify(buildPrescriptionPayload())
        });
        if (!response.ok) throw new Error('Rapport PDF indisponible');
        const blob = await response.blob();
        window.open(URL.createObjectURL(blob), '_blank');
        showToast('Rapport PDF ordonnance ouvert', 'success');
      } catch (e) {
        $('rxResult').textContent = e.message || String(e);
        showToast('Erreur rapport PDF ordonnance', 'error');
      } finally {
        setLoading(btn, false);
      }
    }

    async function createBnplSchedule(btn) {
      setLoading(btn, true);
      try {
        const payload = {
          patient_ref: $('bnplPatientRef').value,
          total_amount_xof: Number($('bnplTotal').value),
          installment_months: Number($('bnplMonths').value),
          prescriber_id: $('bnplPrescriber').value || null
        };
        const data = await api('/billing/bnpl/schedule', {
          method: 'POST',
          headers: headers(),
          body: JSON.stringify(payload)
        });
        $('bnplScheduleId').value = data.id;
        $('bnplAmount').value = data.monthly_amount_xof;
        $('bnplResult').textContent = JSON.stringify(data, null, 2);
        showToast(`Plan BNPL #${data.id} créé`, 'success');
      } catch (e) {
        $('bnplResult').textContent = e.message || String(e);
        showToast('Erreur création BNPL', 'error');
      } finally {
        setLoading(btn, false);
      }
    }

    async function payBnplInstallment(btn) {
      setLoading(btn, true);
      try {
        const scheduleId = $('bnplScheduleId').value;
        const payload = {
          schedule_id: Number(scheduleId),
          installment_number: Number($('bnplInstallment').value),
          amount_xof: Number($('bnplAmount').value)
        };
        const data = await api(`/billing/bnpl/schedule/${scheduleId}/pay`, {
          method: 'POST',
          headers: headers(),
          body: JSON.stringify(payload)
        });
        $('bnplResult').textContent = JSON.stringify(data, null, 2);
        showToast('Paiement BNPL enregistré', 'success');
      } catch (e) {
        $('bnplResult').textContent = e.message || String(e);
        showToast('Erreur paiement BNPL', 'error');
      } finally {
        setLoading(btn, false);
      }
    }

    async function loadBnplSummary(btn) {
      setLoading(btn, true);
      try {
        const data = await api(`/billing/bnpl/summary/${$('bnplScheduleId').value}`, { headers: headers(false) });
        $('bnplResult').textContent = JSON.stringify(data, null, 2);
      } catch (e) {
        $('bnplResult').textContent = e.message || String(e);
        showToast('Erreur résumé BNPL', 'error');
      } finally {
        setLoading(btn, false);
      }
    }

    async function loadOverdueBnpl(btn) {
      setLoading(btn, true);
      try {
        const data = await api('/billing/bnpl/overdue', { headers: headers(false) });
        $('bnplResult').textContent = JSON.stringify(data, null, 2);
        showToast(`${data.length ?? 0} plan(s) en retard`, 'success');
      } catch (e) {
        $('bnplResult').textContent = e.message || String(e);
        showToast('Erreur retards BNPL', 'error');
      } finally {
        setLoading(btn, false);
      }
    }

    // ── Épidémiologie ───────────────────────────────────────────────────────────
    async function loadEpidemio(btn) {
      if (btn) setLoading(btn, true);
      try {
        const body = {};
        if ($('epiStart').value) body.start_date = $('epiStart').value;
        if ($('epiEnd').value) body.end_date = $('epiEnd').value;
        const params = $('epiParams').value.trim();
        if (params) body.parameters = params.split(',').map(s => s.trim()).filter(Boolean);

        const d = await api('/api/v1/epidemiology/dashboard', {
          method: 'POST',
          headers: headers(),
          body: JSON.stringify(body)
        });

        $('epiTotal').textContent = d.total_results;
        $('epiCritical').textContent = d.total_critical;
        $('epiRate').textContent = (d.overall_critical_rate * 100).toFixed(1) + '%';

        renderEpiChart(d.daily_critical_trend);

        setRows('epiParamTable', (d.parameter_stats || []).map(p => row(
          `<td><strong>${p.parameter}</strong></td>` +
          `<td>${p.total_results}</td>` +
          `<td>${p.critical_count}</td>` +
          `<td>${(p.critical_rate * 100).toFixed(1)}%</td>` +
          `<td>${p.mean_value != null ? p.mean_value.toFixed(2) : '—'}</td>` +
          `<td>${p.min_value != null ? p.min_value : '—'}</td>` +
          `<td>${p.max_value != null ? p.max_value : '—'}</td>`
        )));

        setRows('epiFacilityTable', (d.facility_stats || []).map(f => row(
          `<td>${f.facility_name ?? '—'} <span class="pill">#${f.facility_id ?? '?'}</span></td>` +
          `<td>${f.total_results}</td>` +
          `<td>${f.critical_count}</td>` +
          `<td>${(f.critical_rate * 100).toFixed(1)}%</td>`
        )));

        showToast('Tableau épidémiologique actualisé', 'success');
      } catch (e) {
        showToast('Erreur épidémiologie', 'error');
      } finally {
        if (btn) setLoading(btn, false);
      }
    }

    function renderEpiChart(trend) {
      const svg = $('epiChart');
      if (!svg) return;
      if (!trend || trend.length === 0) {
        svg.innerHTML = '<text x="50%" y="50%" text-anchor="middle" fill="var(--muted)" font-size="13">Aucune donnée</text>';
        return;
      }
      const H = 180;
      const pad = { top: 16, right: 16, bottom: 36, left: 36 };
      const W = svg.getBoundingClientRect().width || 380;
      const chartW = W - pad.left - pad.right;
      const chartH = H - pad.top - pad.bottom;
      const maxC = Math.max(...trend.map(d => d.count), 1);
      const n = trend.length;
      const xS = (i) => pad.left + (n > 1 ? (i / (n - 1)) * chartW : chartW / 2);
      const yS = (v) => pad.top + chartH - (v / maxC) * chartH;

      const pts = trend.map((d, i) => `${xS(i).toFixed(1)},${yS(d.count).toFixed(1)}`).join(' ');
      const area = `${xS(0).toFixed(1)},${(pad.top + chartH).toFixed(1)} ${pts} ${xS(n - 1).toFixed(1)},${(pad.top + chartH).toFixed(1)}`;

      const labelIdx = n <= 8 ? trend.map((_, i) => i) : [0, Math.floor(n / 4), Math.floor(n / 2), Math.floor(3 * n / 4), n - 1];
      const xLabels = labelIdx.map(i => {
        const d = trend[i].date.slice(5); // MM-DD
        return `<text x="${xS(i).toFixed(1)}" y="${H - 4}" text-anchor="middle" font-size="10" fill="var(--muted)">${d}</text>`;
      }).join('');

      const dots = trend.map((d, i) => d.count > 0
        ? `<circle cx="${xS(i).toFixed(1)}" cy="${yS(d.count).toFixed(1)}" r="3" fill="var(--blue)">
             <title>${d.date}: ${d.count} critique(s)</title>
           </circle>`
        : ''
      ).join('');

      const gridlines = [0.25, 0.5, 0.75].map(frac => {
        const gv = Math.round(maxC * frac);
        const gy = yS(gv).toFixed(1);
        return `<line x1="${pad.left}" y1="${gy}" x2="${(pad.left + chartW).toFixed(1)}" y2="${gy}" stroke="var(--line)" stroke-width="1" stroke-dasharray="3,3"/>` +
               `<text x="${(pad.left - 4)}" y="${(parseFloat(gy) + 3).toFixed(0)}" text-anchor="end" font-size="9" fill="var(--muted)">${gv}</text>`;
      }).join('');

      svg.setAttribute('height', H);
      svg.innerHTML = `
        <polygon points="${area}" fill="rgba(37,99,235,0.10)" stroke="none"/>
        ${gridlines}
        <polyline points="${pts}" fill="none" stroke="var(--blue)" stroke-width="2" stroke-linejoin="round" stroke-linecap="round"/>
        ${dots}
        ${xLabels}
        <line x1="${pad.left}" y1="${pad.top}" x2="${pad.left}" y2="${pad.top + chartH}" stroke="var(--line)" stroke-width="1"/>
        <line x1="${pad.left}" y1="${pad.top + chartH}" x2="${pad.left + chartW}" y2="${pad.top + chartH}" stroke="var(--line)" stroke-width="1"/>
        <text x="${pad.left - 4}" y="${pad.top + 4}" text-anchor="end" font-size="10" fill="var(--muted)">${maxC}</text>
        <text x="${pad.left - 4}" y="${pad.top + chartH}" text-anchor="end" font-size="10" fill="var(--muted)">0</text>
      `;
    }

    function exportEpiCsv() {
      window.open('/api/v1/reports/epidemiology-export.csv?days=30', '_blank');
    }

    // ── Pharmacie FHIR ──────────────────────────────────────────────────────────
    function switchPharmTab(tab) {
      const isDispense = tab === 'dispense';
      $('pharmDispense').classList.toggle('hidden', !isDispense);
      $('pharmSupply').classList.toggle('hidden', isDispense);
      $('tabDispense').classList.toggle('secondary', !isDispense);
      $('tabDispense').classList.remove('warn');
      $('tabSupply').classList.toggle('secondary', isDispense);
      if (!isDispense) $('tabDispense').classList.add('secondary');
    }

    let _dlCount = 0;
    function addDrugLine() {
      _dlCount++;
      const div = document.createElement('div');
      div.className = 'panel';
      div.style.cssText = 'margin-bottom:8px;padding:10px;';
      div.innerHTML = `
        <div class="grid3" style="gap:6px;align-items:end;">
          <div><label>DCI (code OMS)</label><input data-dl-dci placeholder="ARTEMETHER-LUMEFANTRINE" /></div>
          <div><label>Quantité</label><input data-dl-qty type="number" min="1" value="1" /></div>
          <div><label>Dose (mg)</label><input data-dl-dose type="number" step="0.1" placeholder="opt." /></div>
        </div>
        <div class="grid3" style="gap:6px;margin-top:6px;align-items:end;">
          <div><label>Fréquence/j</label><input data-dl-freq type="number" min="1" max="24" placeholder="opt." /></div>
          <div><label>Durée (j)</label><input data-dl-dur type="number" min="1" placeholder="opt." /></div>
          <div><label>Voie</label><select data-dl-route><option>oral</option><option>IV</option><option>IM</option><option>SC</option><option>topique</option></select></div>
        </div>
        <button class="danger" style="margin-top:6px;width:100%;padding:5px;" onclick="this.parentNode.remove()">✕ Supprimer</button>
      `;
      $('dspDrugLines').appendChild(div);
    }

    let _slCount = 0;
    function addSupplyLine() {
      _slCount++;
      const div = document.createElement('div');
      div.className = 'panel';
      div.style.cssText = 'margin-bottom:8px;padding:10px;';
      div.innerHTML = `
        <div class="grid3" style="gap:6px;align-items:end;">
          <div><label>DCI (code OMS)</label><input data-sl-dci placeholder="ARTEMETHER-LUMEFANTRINE" /></div>
          <div><label>Qté livrée</label><input data-sl-qty type="number" min="1" value="1" /></div>
          <div><label>Coût unit. XOF</label><input data-sl-cost type="number" step="1" placeholder="opt." /></div>
        </div>
        <div class="grid2" style="gap:6px;margin-top:6px;align-items:end;">
          <div><label>N° lot</label><input data-sl-batch placeholder="LOT-2026-001 (opt.)" /></div>
          <div><label>Date péremption</label><input data-sl-expiry type="date" /></div>
        </div>
        <button class="danger" style="margin-top:6px;width:100%;padding:5px;" onclick="this.parentNode.remove()">✕ Supprimer</button>
      `;
      $('supItemLines').appendChild(div);
    }

    async function submitDispense(btn) {
      setLoading(btn, true);
      try {
        const drugLines = [];
        Array.from($('dspDrugLines').children).forEach(panel => {
          const dci = panel.querySelector('[data-dl-dci]')?.value?.trim();
          const qty = panel.querySelector('[data-dl-qty]')?.value;
          if (!dci || !qty) return;
          const line = {
            dci_code: dci,
            quantity: parseInt(qty),
            route: panel.querySelector('[data-dl-route]')?.value || 'oral'
          };
          const dose = panel.querySelector('[data-dl-dose]')?.value;
          const freq = panel.querySelector('[data-dl-freq]')?.value;
          const dur = panel.querySelector('[data-dl-dur]')?.value;
          if (dose) line.dose_mg = parseFloat(dose);
          if (freq) line.frequency_per_day = parseInt(freq);
          if (dur) line.duration_days = parseInt(dur);
          drugLines.push(line);
        });
        if (!drugLines.length) { showToast('Ajoutez au moins un médicament', 'warning'); setLoading(btn, false); return; }
        const payload = {
          patient_ref: $('dspPatientRef').value,
          practitioner_ref: $('dspPractRef').value || null,
          authorizing_prescription_ref: $('dspPrescRef').value || null,
          cnam_billing_ref: $('dspCnamRef').value || null,
          dispensed_at: $('dspDate').value ? new Date($('dspDate').value).toISOString() : null,
          drug_lines: drugLines
        };
        const bundle = await api('/fhir/medication-dispense', { method: 'POST', headers: headers(), body: JSON.stringify(payload) });
        $('dspResult').textContent = JSON.stringify(bundle, null, 2);
        showToast(`Bundle MedicationDispense — ${bundle.entry?.length ?? 0} entrée(s)`, 'success');
      } catch (e) { showToast('Erreur génération bundle MedicationDispense', 'error'); }
      finally { setLoading(btn, false); }
    }

    async function submitSupply(btn) {
      setLoading(btn, true);
      try {
        const items = [];
        Array.from($('supItemLines').children).forEach(panel => {
          const dci = panel.querySelector('[data-sl-dci]')?.value?.trim();
          const qty = panel.querySelector('[data-sl-qty]')?.value;
          if (!dci || !qty) return;
          const item = { dci_code: dci, quantity: parseInt(qty) };
          const cost = panel.querySelector('[data-sl-cost]')?.value;
          const batch = panel.querySelector('[data-sl-batch]')?.value;
          const expiry = panel.querySelector('[data-sl-expiry]')?.value;
          if (cost) item.unit_cost_xof = parseFloat(cost);
          if (batch) item.batch_number = batch;
          if (expiry) item.expiry_date = expiry;
          items.push(item);
        });
        if (!items.length) { showToast('Ajoutez au moins un article', 'warning'); setLoading(btn, false); return; }
        const payload = {
          supplier_name: $('supSupplier').value,
          destination_pharmacy_id: $('supDest').value,
          delivery_date: $('supDate').value || null,
          order_reference: $('supOrderRef').value || null,
          items
        };
        const bundle = await api('/fhir/supply-delivery', { method: 'POST', headers: headers(), body: JSON.stringify(payload) });
        $('supResult').textContent = JSON.stringify(bundle, null, 2);
        showToast(`Bundle SupplyDelivery — ${bundle.entry?.length ?? 0} entrée(s)`, 'success');
      } catch (e) { showToast('Erreur génération bundle SupplyDelivery', 'error'); }
      finally { setLoading(btn, false); }
    }

    async function copyFhirJson(id) {
      const text = $(id)?.textContent;
      if (!text || text === 'Aucun bundle généré.') { showToast('Aucun bundle à copier', 'warning'); return; }
      try {
        await navigator.clipboard.writeText(text);
        showToast('JSON copié dans le presse-papiers', 'success');
      } catch { showToast('Copie impossible (HTTP non sécurisé)', 'error'); }
    }

    // ── Équipements ───────────────────────────────────────────────────────────
    async function loadEquipments() {
      const tbody = $('equipmentsTable')?.querySelector('tbody');
      if (!tbody) return;
      loadingStates.showSkeleton(tbody, 5);
      try {
        const data = await api('/api/v1/equipments', { headers: headers(false) });
        setRows('equipmentsTable', data.map(e => row(
          `<td>${e.id}</td>` +
          `<td><strong>${security.escapeHtml(e.name)}</strong></td>` +
          `<td>${security.escapeHtml(e.type || '—')}</td>` +
          `<td>${security.escapeHtml(e.serial_number || '—')}</td>` +
          `<td>${security.escapeHtml(e.location || '—')}</td>` +
          `<td>${e.last_calibration || '—'}</td>`
        )));
      } catch {
        if (tbody) tbody.innerHTML = '<tr><td colspan="6" style="text-align:center;color:var(--rose);">Erreur chargement équipements</td></tr>';
      }
    }

    async function createEquipment(btn) {
      $('eqFormError').textContent = '';
      setLoading(btn, true);
      try {
        const name = $('eqName').value.trim();
        if (!name) throw new Error('Le nom est obligatoire');
        const payload = {
          name,
          type: $('eqType').value.trim() || null,
          serial_number: $('eqSerial').value.trim() || null,
          location: $('eqLocation').value.trim() || null,
          last_calibration: $('eqCalib').value || null,
        };
        await api('/api/v1/equipments', { method: 'POST', headers: headers(), body: JSON.stringify(payload) });
        showToast(`Équipement « ${security.escapeHtml(name)} » enregistré`, 'success');
        ['eqName', 'eqType', 'eqSerial', 'eqLocation', 'eqCalib'].forEach(id => { if ($(id)) $(id).value = ''; });
        await loadEquipments();
      } catch (e) {
        $('eqFormError').textContent = e.message || 'Erreur inconnue';
        showToast(e.message || 'Erreur création équipement', 'error');
      } finally {
        setLoading(btn, false);
      }
    }

    // ── Journal d'audit ───────────────────────────────────────────────────────
    let _auditSkip = 0;
    const _auditLimit = 50;

    function _auditFilterQuery() {
      const p = new URLSearchParams();
      const et = $('auditFilterEventType')?.value.trim();
      const en = $('auditFilterEntityType')?.value.trim();
      const us = $('auditFilterUser')?.value.trim();
      const df = $('auditFilterFrom')?.value;
      const dt2 = $('auditFilterTo')?.value;
      if (et) p.set('event_type', et);
      if (en) p.set('entity_type', en);
      if (us) p.set('username', us);
      if (df) p.set('date_from', df);
      if (dt2) p.set('date_to', dt2);
      return p.toString();
    }
    function applyAuditFilters() { _auditSkip = 0; loadAudit(); }
    function resetAuditFilters() {
      ['auditFilterEventType','auditFilterEntityType','auditFilterUser','auditFilterFrom','auditFilterTo']
        .forEach(id => { if ($(id)) $(id).value = ''; });
      _auditSkip = 0; loadAudit();
    }
    async function exportAuditCsv() {
      try {
        const fq = _auditFilterQuery();
        const resp = await fetch(normalizeApiPath('/api/v1/audit-events/export.csv' + (fq ? '?' + fq : '')), { headers: headers(false) });
        if (!resp.ok) { showToast('Export refusé (droits admin requis)', 'error'); return; }
        const blob = await resp.blob();
        const url = URL.createObjectURL(blob);
        const a = document.createElement('a');
        a.href = url; a.download = 'audit-export.csv'; a.click();
        URL.revokeObjectURL(url);
        showToast('Export CSV téléchargé', 'success');
      } catch { showToast('Erreur export CSV', 'error'); }
    }
    async function loadAudit() {
      const tbody = $('auditTable')?.querySelector('tbody');
      if (!tbody) return;
      loadingStates.showSkeleton(tbody, 5);
      try {
        const fq = _auditFilterQuery();
        const data = await api(`/api/v1/audit-events?skip=${_auditSkip}&limit=${_auditLimit}${fq ? '&' + fq : ''}`, { headers: headers(false) });
        const fmt = d => d ? new Date(d).toLocaleString('fr-FR') : '—';
        const typeLabel = {
          'user.create':    '👤 Création user',
          'user.update':    '✏️ Modif. user',
          'reagent.create': '🧪 Nouveau réactif',
          'reagent.update': '✏️ Modif. réactif',
          'reagent.delete': '🗑️ Suppression réactif',
          'result.amend':   '✏️ Correction résultat',
        };
        setRows('auditTable', (data.items || []).map(e => row(
          `<td>${e.id}</td>` +
          `<td style="white-space:nowrap;">${fmt(e.created_at)}</td>` +
          `<td><strong>${security.escapeHtml(e.username || '—')}</strong></td>` +
          `<td>${typeLabel[e.event_type] || security.escapeHtml(e.event_type)}</td>` +
          `<td>${security.escapeHtml(e.entity_type)}</td>` +
          `<td>${security.escapeHtml(e.entity_id || '—')}</td>`
        )));
        const m = data.meta || {};
        if ($('auditPagerInfo')) {
          const from = _auditSkip + 1;
          const to = Math.min(_auditSkip + _auditLimit, m.total || 0);
          $('auditPagerInfo').textContent = `Événements ${from}–${to} sur ${m.total || 0}`;
        }
      } catch {
        if (tbody) tbody.innerHTML = '<tr><td colspan="6" style="text-align:center;color:var(--rose);">Droits admin requis</td></tr>';
      }
    }

    function auditPage(dir) {
      _auditSkip = Math.max(0, _auditSkip + dir * _auditLimit);
      loadAudit();
    }

    // ── Gestion des utilisateurs ──────────────────────────────────────────────
    let _editingUserId = null;
    let _samplesCache  = [];   // cache pour scan express
    let _patientsCache = {};   // { id → patient } partagé entre scan et impression

    async function loadUsers() {
      const tbody = $('usersTable')?.querySelector('tbody');
      if (!tbody) return;
      loadingStates.showSkeleton(tbody, 4);
      try {
        const data = await api('/api/v1/users', { headers: headers(false) });
        const roleLabel = { admin: '🔴 Admin', officer: '🟡 Officier', technician: '🟢 Tech.' };
        const rolePill  = { admin: 'bad',       officer: 'warn',         technician: 'ok' };
        const rows = data.map(u => {
          const tr = row(
            `<td>${u.id}</td>` +
            `<td><strong>${security.escapeHtml(u.username)}</strong></td>` +
            `<td>${security.escapeHtml(u.full_name || '—')}</td>` +
            `<td><span class="pill ${rolePill[u.role] || ''}">${roleLabel[u.role] || u.role}</span></td>` +
            `<td>${u.is_active ? '<span class="pill ok">Oui</span>' : '<span class="pill bad">Non</span>'}</td>` +
            `<td style="white-space:nowrap;">` +
              `<button class="ghost" style="margin-right:4px;" onclick='selectUserForEdit(${JSON.stringify(u)})'>Éditer</button>` +
              `<button class="${u.is_active ? 'warn' : 'success'}" onclick="toggleUserActive(${u.id},${u.is_active})">${u.is_active ? 'Désactiver' : 'Activer'}</button>` +
            `</td>`
          );
          if (!u.is_active) tr.style.opacity = '0.55';
          return tr;
        });
        setRows('usersTable', rows);
      } catch {
        if (tbody) tbody.innerHTML = '<tr><td colspan="6" style="text-align:center;color:var(--rose);">Erreur — droits admin requis</td></tr>';
      }
    }

    function selectUserForEdit(u) {
      _editingUserId = u.id;
      $('userUsername').value = u.username;
      $('userUsername').disabled = true;
      $('userPassword').value = '';
      $('userPassword').placeholder = 'Laisser vide = inchangé';
      $('userFullName').value = u.full_name || '';
      $('userRole').value = u.role;
      $('userFormTitle').textContent = `Modifier — ${u.username}`;
      $('userSubmitBtn').textContent = 'Enregistrer';
      $('userCancelBtn').style.display = '';
      $('userFormError').textContent = '';
      $('userFormTitle').scrollIntoView({ behavior: 'smooth', block: 'center' });
    }

    function resetUserForm() {
      _editingUserId = null;
      $('userUsername').value = '';
      $('userUsername').disabled = false;
      $('userPassword').value = '';
      $('userPassword').placeholder = 'Min. 8 caractères';
      $('userFullName').value = '';
      $('userRole').value = 'technician';
      $('userFormTitle').textContent = 'Nouvel utilisateur';
      $('userSubmitBtn').textContent = 'Créer utilisateur';
      $('userCancelBtn').style.display = 'none';
      $('userFormError').textContent = '';
    }

    async function submitUserForm(btn) {
      $('userFormError').textContent = '';
      setLoading(btn, true);
      try {
        if (_editingUserId) {
          // PATCH — rôle, nom complet, et mot de passe optionnel
          const payload = {
            full_name: $('userFullName').value.trim() || null,
            role: $('userRole').value,
            unit: ($('userUnit')?.value || '').trim() || null,
          };
          const pw = $('userPassword').value;
          if (pw) {
            if (pw.length < 8) throw new Error('Mot de passe trop court (min. 8 caractères)');
            payload.password = pw;
          }
          await api(`/api/v1/users/${_editingUserId}`, {
            method: 'PATCH', headers: headers(), body: JSON.stringify(payload),
          });
          showToast('Utilisateur mis à jour', 'success');
          resetUserForm();
        } else {
          // POST — création
          const username = $('userUsername').value.trim();
          const password = $('userPassword').value;
          if (username.length < 3) throw new Error('Identifiant trop court (min. 3 caractères)');
          if (password.length < 8) throw new Error('Mot de passe trop court (min. 8 caractères)');
          const payload = {
            username,
            password,
            full_name: $('userFullName').value.trim() || null,
            role: $('userRole').value,
            unit: ($('userUnit')?.value || '').trim() || null,
          };
          const created = await api('/api/v1/users', {
            method: 'POST', headers: headers(), body: JSON.stringify(payload),
          });
          showToast(`Utilisateur « ${created.username} » créé`, 'success');
          resetUserForm();
        }
        await loadUsers();
      } catch (e) {
        $('userFormError').textContent = e.message || 'Erreur inconnue';
      } finally {
        setLoading(btn, false);
      }
    }

    function toggleUserPw() {
      const inp = $('userPassword');
      if (inp) inp.type = inp.type === 'text' ? 'password' : 'text';
    }

    async function toggleUserActive(id, currentActive) {
      try {
        await api(`/api/v1/users/${id}`, {
          method: 'PATCH', headers: headers(),
          body: JSON.stringify({ is_active: !currentActive }),
        });
        showToast(currentActive ? 'Utilisateur désactivé' : 'Utilisateur réactivé',
                  currentActive ? 'warning' : 'success');
        await loadUsers();
      } catch {
        showToast('Erreur modification statut', 'error');
      }
    }

    // ── Workflow statut échantillon ───────────────────────────────────────────
    async function advanceSampleStatus(id, newStatus) {
      try {
        await api(`/api/v1/samples/${id}`, {
          method: 'PATCH', headers: headers(), body: JSON.stringify({ status: newStatus }),
        });
        showToast(`Statut → ${newStatus}`, 'success');
        await loadSamples();
      } catch (e) {
        showToast(e.message || 'Erreur mise à jour statut', 'error');
      }
    }

    // ── Scan express barcode ──────────────────────────────────────────────────
    async function scanBarcode(code) {
      if (!code) return;
      // Chercher dans le cache local ; si absent, rafraîchir puis réessayer
      let found = _samplesCache.find(s => s.barcode === code);
      if (!found) {
        await loadSamples();
        found = _samplesCache.find(s => s.barcode === code);
      }
      const resultDiv = $('scanResult');
      if (!found) {
        resultDiv.innerHTML =
          '<div style="color:var(--rose);font-size:13px;padding:6px 0;">❌ Code-barres inconnu : <code>' +
          security.escapeHtml(code) + '</code></div>';
        resultDiv.style.display = '';
        return;
      }
      const p = _patientsCache[found.patient_id] || null;
      const labelData = {
        barcode: found.barcode,
        patient: p ? (p.first_name + ' ' + p.last_name) : (found.patient_id ? 'Patient #' + found.patient_id : '—'),
        ipp:  p ? p.ipp_unique_id      : '',
        sex:  p ? (p.sex || '')        : '',
        dob:  p ? (p.birth_date || '') : '',
        date: found.collection_date ? found.collection_date.slice(0, 10) : '',
        exam: found.status || '',
      };
      resultDiv.innerHTML =
        '<div style="display:flex;align-items:center;gap:12px;flex-wrap:wrap;' +
            'background:var(--band);border:2px solid var(--teal);border-radius:8px;padding:10px;">' +
          '<div>' +
            '<div style="font-size:13px;font-weight:700;">✅ ' + security.escapeHtml(found.barcode) + '</div>' +
            '<div style="font-size:12px;color:var(--muted);">' +
              (p ? security.escapeHtml(p.first_name + ' ' + p.last_name) + ' · ' + security.escapeHtml(p.ipp_unique_id)
                 : 'Patient #' + (found.patient_id || '?')) +
            '</div>' +
            '<div style="font-size:12px;">Statut : ' + security.escapeHtml(found.status || '—') + '</div>' +
          '</div>' +
          '<div class="actions" style="margin-left:auto;">' +
            '<button class="ghost" onclick=\'printSampleLabel(' + JSON.stringify(labelData) + ')\'>🖨️ Étiquette</button>' +
            '<button class="secondary" onclick="showView(\'results\')">📋 Résultats</button>' +
          '</div>' +
        '</div>';
      resultDiv.style.display = '';
      const inp = $('barcodeScanner');
      if (inp) inp.value = '';
    }

    function clearScanResult() {
      const r = $('scanResult');
      if (r) { r.innerHTML = ''; r.style.display = 'none'; }
      const inp = $('barcodeScanner');
      if (inp) { inp.value = ''; inp.focus(); }
    }

    // ── Impression étiquettes tubes ───────────────────────────────────────────
    /**
     * Ouvre une fenêtre dédiée avec des étiquettes imprimables.
     * Supporte : choix du format, nombre de copies, et code couleur tube.
     * @param {Array<{barcode,patient,ipp,sex,dob,date,exam}>} labels
     */
    function printTubeLabels(labels) {
      if (!labels || !labels.length) {
        showToast('Aucun échantillon à imprimer', 'warning');
        return;
      }
      // Les données sont sérialisées en JSON et injectées dans le popup
      const labelsJson = JSON.stringify(labels).replace(/<\/script>/gi, '<\\/script>');

      const html = `<!DOCTYPE html>
<html lang="fr">
<head>
<meta charset="utf-8"/>
<title>Etiquettes tubes - RuggyLab OS</title>
<script src="https://cdn.jsdelivr.net/npm/jsbarcode@3.11.6/dist/JsBarcode.all.min.js"><\/script>
<style id="baseStyle">
  *{box-sizing:border-box;margin:0;padding:0;}
  body{font-family:Arial,Helvetica,sans-serif;color:#000000;background:#f0f0f0;padding:12px;}
  .ctrl{display:flex;flex-wrap:wrap;align-items:center;gap:10px;padding:10px;background:#fff;
        border:1px solid #ddd;border-radius:6px;margin-bottom:12px;}
  .ctrl label{font-size:12px;font-weight:600;display:flex;align-items:center;gap:5px;}
  .ctrl select,.ctrl input[type=number]{padding:4px 6px;border:1px solid #ccc;border-radius:4px;font-size:12px;}
  .ctrl input[type=number]{width:54px;}
  .ctrl button{padding:7px 14px;border:none;border-radius:5px;cursor:pointer;font-size:12px;
               font-weight:600;color:#fff;background:#2563eb;}
  .ctrl button.sec{background:#64748b;}
  .ctrl .info{font-size:11px;color:#888;margin-left:auto;}
  .labels{display:flex;flex-wrap:wrap;gap:8px;}
  /* base label — dimensions mises a jour par dynStyle */
  .label{background:#fff;border:1px solid #bbb;border-radius:3px;width:56mm;padding:2mm;
         display:flex;flex-direction:column;align-items:center;gap:1px;page-break-inside:avoid;overflow:hidden;}
  /* Bande couleur tube (④) */
  .tube-band{width:100%;height:4mm;border-radius:1px;margin-bottom:1.5mm;
             display:flex;align-items:center;justify-content:center;}
  .tube-band-lbl{font-size:6pt;font-weight:700;color:#fff;letter-spacing:.5px;}
  /* Typographie : Arial, noir pur */
  .pname{font-family:Arial,Helvetica,sans-serif;font-size:8.5pt;font-weight:700;
         color:#000000;text-align:center;line-height:1.2;}
  .ipp  {font-family:Arial,Helvetica,sans-serif;font-size:7pt;color:#000000;text-align:center;}
  .bcsvg{width:52mm;height:13mm;}
  .bcval{font-family:Arial,Helvetica,monospace;font-size:7pt;letter-spacing:1px;color:#000000;}
  .meta {font-family:Arial,Helvetica,sans-serif;font-size:7pt;color:#000000;}
  @media print{body{background:#fff;padding:0;}.ctrl{display:none;}.labels{gap:0;}
    .label{border:none;}}
</style>
<style id="dynStyle"></style>
</head>
<body>
<div class="ctrl">
  <label>Format :
    <select id="fmtSel" onchange="renderLabels()">
      <option value="56x21" selected>Tube standard 56x21 mm</option>
      <option value="38x13">Micro-tube 38x13 mm</option>
      <option value="102x38">Pot / conteneur 102x38 mm</option>
    </select>
  </label>
  <label>Copies / tube :
    <input type="number" id="copiesSel" value="1" min="1" max="9" onchange="renderLabels()" />
  </label>
  <button onclick="window.print()">Imprimer</button>
  <button class="sec" onclick="window.close()">Fermer</button>
  <span class="info" id="pgInfo"></span>
</div>
<div id="labelsContainer" class="labels"></div>
<script>
var LABELS = ${labelsJson};
var FORMATS = {
  '56x21' :{w:'56mm',h:'21mm',svgW:'52mm',svgH:'13mm',fs:'8.5pt',fss:'7pt', pad:'2mm',  bh:36},
  '38x13' :{w:'38mm',h:'13mm',svgW:'34mm',svgH:'7mm', fs:'6pt',  fss:'5.5pt',pad:'1.5mm',bh:20},
  '102x38':{w:'102mm',h:'38mm',svgW:'96mm',svgH:'22mm',fs:'10pt',fss:'8.5pt',pad:'3mm', bh:55}
};
/* ④ Correspondance examen → couleur bouchon tube */
var TUBE = [
  {p:['nfs','hgb','wbc','plt','rbc','mal'], e:['nfs','paludisme','malaria'],  c:'#7c3aed',n:'EDTA'},
  {p:['bch','poc','glc','cre','alb'],       e:['biochimie','poct'],           c:'#d97706',n:'SST'},
  {p:['coag','tp','tca','inr'],             e:['coagulation'],                c:'#2563eb',n:'Citrate'},
  {p:['ur','ban'],                          e:['urine','urines','bandelette'], c:'#eab308',n:'Urine'}
];
function tubeInfo(barcode,exam){
  var b=(barcode||'').toLowerCase(),e=(exam||'').toLowerCase();
  for(var i=0;i<TUBE.length;i++){
    var t=TUBE[i];
    if(t.p.some(function(x){return b.indexOf(x)===0;})||t.e.some(function(x){return e.indexOf(x)>=0;}))
      return {c:t.c,n:t.n};
  }
  return {c:'#6b7280',n:''};
}
function esc(s){return String(s==null?'':s).replace(/[&<>"']/g,function(c){return({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c]);});}
function renderLabels(){
  var fk=document.getElementById('fmtSel').value;
  var f=FORMATS[fk]||FORMATS['56x21'];
  var copies=Math.max(1,Math.min(9,parseInt(document.getElementById('copiesSel').value)||1));
  /* Mettre a jour le CSS dynamique (@page, dimensions) */
  document.getElementById('dynStyle').textContent=
    '@media print{@page{size:'+f.w+' '+f.h+';margin:0;}}'+
    '.label{width:'+f.w+';min-height:'+f.h+';padding:'+f.pad+';}'+
    '.bcsvg{width:'+f.svgW+';height:'+f.svgH+';}'+
    '.pname{font-size:'+f.fs+';}'+
    '.ipp,.bcval,.meta{font-size:'+f.fss+';}';
  /* Generer les cartes (copies x labels) */
  var expanded=[];
  for(var c=0;c<copies;c++) for(var j=0;j<LABELS.length;j++) expanded.push(LABELS[j]);
  document.getElementById('labelsContainer').innerHTML=expanded.map(function(l,i){
    var t=tubeInfo(l.barcode,l.exam);
    return '<div class="label">'+
      '<div class="tube-band" style="background:'+t.c+';">'+
        '<span class="tube-band-lbl">'+esc(t.n)+'</span>'+
      '</div>'+
      '<div class="pname">'+esc(l.patient)+'</div>'+
      '<div class="ipp">'+esc(l.ipp)+(l.sex?' &bull; '+esc(l.sex):'')+(l.dob?' &bull; '+esc(l.dob):'')+'</div>'+
      '<svg id="bcd'+i+'" class="bcsvg"></svg>'+
      '<div class="bcval">'+esc(l.barcode)+'</div>'+
      (l.date||l.exam?'<div class="meta">'+esc(l.date)+(l.exam?' &mdash; '+esc(l.exam):'')+'</div>':'')+
    '</div>';
  }).join('');
  /* Rendre les codes-barres Code128 */
  expanded.forEach(function(l,i){
    try{
      JsBarcode('#bcd'+i,l.barcode,{
        format:'CODE128',lineColor:'#000000',background:'#ffffff',
        width:1.6,height:f.bh,displayValue:false,margin:4
      });
    }catch(e){
      var el=document.getElementById('bcd'+i);
      if(el) el.outerHTML='<div style="font-size:8px;color:red;">Err barcode</div>';
    }
  });
  var n=expanded.length;
  document.getElementById('pgInfo').textContent=
    n+' etiquette'+(n>1?'s':'')+' - '+copies+' copie'+(copies>1?'s':'')+' / tube';
}
window.onload=renderLabels;
<\/script>
</body>
</html>`;
      const win = window.open('', '_blank', 'width=920,height=720,menubar=no,toolbar=no');
      if (!win) { showToast('Popup bloque par le navigateur — autorisez les popups', 'error'); return; }
      win.document.write(html);
      win.document.close();
    }

    /** Récupère tous les échantillons d'un patient et ouvre la feuille d'étiquettes */
    async function printPatientLabels(p) {
      try {
        const data = await api('/api/v1/samples', { headers: headers(false) });
        const patientSamples = (data.items || []).filter(s => s.patient_id === p.id);
        if (!patientSamples.length) {
          showToast(`Aucun échantillon enregistré pour ${p.first_name} ${p.last_name}`, 'warning');
          return;
        }
        printTubeLabels(patientSamples.map(s => ({
          barcode: s.barcode,
          patient: `${p.first_name} ${p.last_name}`,
          ipp: p.ipp_unique_id,
          sex: p.sex || '',
          dob: p.birth_date || '',
          date: s.collection_date ? s.collection_date.slice(0, 10) : '',
          exam: s.status || '',
        })));
      } catch {
        showToast('Erreur récupération échantillons', 'error');
      }
    }

    /** Imprime l'étiquette d'un échantillon individuel.
     *  labelData est déjà enrichi (patient, ipp, sex, dob) depuis loadSamples() ou scanBarcode(). */
    function printSampleLabel(labelData) {
      printTubeLabels([labelData]);
    }

    // ══════════════════════════════════════════════════════════════
    //  Maintenance équipements
    // ══════════════════════════════════════════════════════════════
    async function loadMaintenances() {
      const tbody = $('maintenanceTable')?.querySelector('tbody');
      if (!tbody) return;
      loadingStates.showSkeleton(tbody, 4);
      try {
        const data = await api('/api/v1/equipment-maintenance?limit=50', { headers: headers(false) });
        const fmt = d => d ? new Date(d).toLocaleDateString('fr-FR', { day: '2-digit', month: '2-digit', year: 'numeric' }) : '—';
        const typeLabel = { preventive: '🔧 Préventive', corrective: '🚨 Corrective', calibration: '📐 Étalonnage' };
        const now = Date.now();
        const sevenDays = 7 * 86400 * 1000;
        setRows('maintenanceTable', data.map(m => {
          const isDue = m.next_due_at && !m.is_completed && (new Date(m.next_due_at).getTime() - now) <= sevenDays;
          const isOverdue = m.next_due_at && !m.is_completed && new Date(m.next_due_at) < new Date();
          const dueCell = m.next_due_at
            ? (isOverdue ? `<span class="pill bad">${fmt(m.next_due_at)} ⚠</span>`
               : isDue ? `<span class="pill warn">${fmt(m.next_due_at)}</span>`
               : fmt(m.next_due_at))
            : '—';
          const tr = row(
            `<td><strong>${m.equipment_id}</strong></td>` +
            `<td>${typeLabel[m.maintenance_type] || security.escapeHtml(m.maintenance_type)}</td>` +
            `<td>${fmt(m.scheduled_at)}</td>` +
            `<td>${dueCell}</td>` +
            `<td>${m.is_completed ? '<span class="pill ok">✓ Terminée</span>' : '<span class="pill">En attente</span>'}</td>` +
            `<td class="actions" style="white-space:nowrap;">` +
              (!m.is_completed ? `<button class="success" style="font-size:11px;padding:3px 8px;" onclick="completeMaintenance(${m.id},this)" title="Marquer terminée">✓</button> ` : '') +
              `<button class="danger" style="font-size:11px;padding:3px 8px;" onclick="deleteMaintenance(${m.id},this)" title="Supprimer">✕</button>` +
            `</td>`
          );
          if (isOverdue) tr.classList.add('row-critical');
          else if (isDue) tr.classList.add('row-warning');
          if (m.is_completed) tr.style.opacity = '0.55';
          return tr;
        }));
      } catch {
        if (tbody) tbody.innerHTML = '<tr><td colspan="6" style="text-align:center;color:var(--rose);">Erreur chargement maintenance</td></tr>';
      }
    }

    async function createMaintenance(btn) {
      setLoading(btn, true);
      try {
        const eqId = parseInt($('mntEqId')?.value || '0');
        if (!eqId) throw new Error("L'identifiant équipement est requis");
        const payload = {
          equipment_id: eqId,
          maintenance_type: $('mntType')?.value || 'preventive',
          scheduled_at: $('mntScheduled')?.value ? new Date($('mntScheduled').value).toISOString() : null,
          next_due_at: $('mntNextDue')?.value ? new Date($('mntNextDue').value).toISOString() : null,
          notes: $('mntNotes')?.value?.trim() || null,
        };
        await api('/api/v1/equipment-maintenance', { method: 'POST', headers: headers(), body: JSON.stringify(payload) });
        showToast('Maintenance planifiée avec succès', 'success');
        ['mntEqId', 'mntScheduled', 'mntNextDue', 'mntNotes'].forEach(id => { if ($(id)) $(id).value = ''; });
        await loadMaintenances();
      } catch (e) {
        showToast(e.message || 'Erreur création maintenance', 'error');
      } finally {
        setLoading(btn, false);
      }
    }

    async function completeMaintenance(id, btn) {
      setLoading(btn, true);
      try {
        await api(`/api/v1/equipment-maintenance/${id}/complete`, { method: 'PATCH', headers: headers() });
        showToast('Maintenance marquée comme terminée', 'success');
        await loadMaintenances();
      } catch (e) {
        showToast(e.message || 'Erreur', 'error');
      } finally {
        setLoading(btn, false);
      }
    }

    async function deleteMaintenance(id, btn) {
      if (!confirm('Supprimer cette entrée de maintenance ?')) return;
      setLoading(btn, true);
      try {
        await api(`/api/v1/equipment-maintenance/${id}`, { method: 'DELETE', headers: headers() });
        showToast('Maintenance supprimée', 'success');
        await loadMaintenances();
      } catch (e) {
        showToast(e.message || 'Erreur', 'error');
      } finally {
        setLoading(btn, false);
      }
    }

    // ══════════════════════════════════════════════════════════════
    //  Statistiques de performance laboratoire
    // ══════════════════════════════════════════════════════════════
    async function loadStats() {
      const days = $('statsDays')?.value || 30;
      try {
        const data = await api(`/api/v1/stats/summary?days=${days}`, { headers: headers(false) });

        $('statTotal').textContent = data.total_results ?? '—';

        // Taux critique
        const critPct = data.critical_rate_pct ?? 0;
        if ($('statCrit')) $('statCrit').textContent = critPct + ' %';
        const cp = $('statCritPanel');
        if (cp) {
          cp.classList.remove('metric-rose', 'metric-amber', 'metric-teal');
          cp.classList.add(critPct > 10 ? 'metric-rose' : critPct > 3 ? 'metric-amber' : 'metric-teal');
        }

        // Violations QC
        const qcPct = data.qc_violation_rate_pct ?? 0;
        if ($('statQc')) $('statQc').textContent = qcPct + ' %';
        const qp = $('statQcPanel');
        if (qp) {
          qp.classList.remove('metric-rose', 'metric-amber', 'metric-teal');
          qp.classList.add(qcPct > 10 ? 'metric-rose' : qcPct > 0 ? 'metric-amber' : 'metric-teal');
        }

        // Maintenance due
        const mnt = data.maintenance_due_count ?? 0;
        if ($('statMnt')) $('statMnt').textContent = mnt;
        const mp = $('statMntPanel');
        if (mp) {
          mp.classList.remove('metric-amber', 'metric-teal', 'metric-rose');
          mp.classList.add(mnt > 0 ? 'metric-amber' : 'metric-teal');
        }

        // Graphes
        _renderTatChart(data.tat_by_equipment || []);
        _renderWeeklyChart(data.weekly_volumes || []);

        // Tableau détail TAT
        setRows('tatDetailTable', (data.tat_by_equipment || []).map(d => row(
          `<td><strong>${security.escapeHtml(d.equipment)}</strong></td>` +
          `<td>${d.count}</td>` +
          `<td style="font-variant-numeric:tabular-nums;">${d.mean_h}</td>` +
          `<td>${d.min_h}</td>` +
          `<td>${d.max_h}</td>` +
          `<td>${d.p95_h}</td>`
        )));

        await loadComplianceTrend();
      } catch (e) {
        showToast('Erreur chargement statistiques', 'error');
        log('loadStats: ' + (e.message || e));
      }
    }

    async function loadComplianceTrend() {
      try {
        const data = await api('/api/v1/reports/compliance-trend?months=12', { headers: headers(false) });
        const badge = $('complianceDriftBadge');
        if (badge) badge.style.display = data.has_drift ? '' : 'none';
        _renderComplianceTrend(data.series || []);
      } catch (e) { log('loadComplianceTrend: ' + (e.message || e)); }
    }
    function _renderComplianceTrend(series) {
      const div = $('complianceTrendChart');
      if (!div) return;
      if (!series.length) { div.innerHTML = '<p style="color:var(--muted);">Aucune donnée.</p>'; return; }
      const W = 720, H = 160, padL = 36, padR = 10, padTop = 12, padBot = 28;
      const chartW = W - padL - padR, chartH = H - padTop - padBot;
      const step = series.length > 1 ? chartW / (series.length - 1) : 0;
      const yFor = v => padTop + chartH - (v / 100) * chartH;
      const pts = series.map((s, i) => `${(padL + i * step).toFixed(1)},${yFor(s.validation_rate_pct).toFixed(1)}`).join(' ');
      const dots = series.map((s, i) => {
        const x = padL + i * step, y = yFor(s.validation_rate_pct);
        const color = s.drift ? '#be123c' : '#0f766e';
        return `<circle cx="${x.toFixed(1)}" cy="${y.toFixed(1)}" r="3" fill="${color}"><title>${s.month}: ${s.validation_rate_pct}%</title></circle>`;
      }).join('');
      const labels = series.map((s, i) => {
        if (series.length > 8 && i % 2 !== 0) return '';
        const x = padL + i * step;
        return `<text x="${x.toFixed(1)}" y="${H - 8}" text-anchor="middle" font-size="9" fill="var(--muted)">${s.month.slice(2)}</text>`;
      }).join('');
      const grid = [0, 50, 99, 100].map(v =>
        `<line x1="${padL}" y1="${yFor(v).toFixed(1)}" x2="${W - padR}" y2="${yFor(v).toFixed(1)}" stroke="#e5e7eb" stroke-width="1"/>` +
        `<text x="2" y="${(yFor(v) + 3).toFixed(1)}" font-size="9" fill="var(--muted)">${v}</text>`
      ).join('');
      div.innerHTML = `<svg viewBox="0 0 ${W} ${H}" width="100%" style="display:block;">${grid}` +
        `<polyline points="${pts}" fill="none" stroke="#2563eb" stroke-width="2"/>${dots}${labels}</svg>` +
        `<p style="font-size:11px;color:var(--muted);margin:4px 0 0;">Taux de validation mensuel (%) · points rouges = sous le seuil de conformité</p>`;
    }
    async function openComplianceReport() {
      try {
        const resp = await fetch(normalizeApiPath('/api/v1/reports/compliance-report?days=30'), { headers: headers(false) });
        if (!resp.ok) { showToast('Rapport indisponible', 'error'); return; }
        const html = await resp.text();
        const w = window.open('', '_blank');
        if (w) { w.document.write(html); w.document.close(); }
        else showToast('Autoriser les pop-ups pour ouvrir le rapport', 'warning');
      } catch { showToast('Erreur rapport conformité', 'error'); }
    }
    function _formatCriticalDelay(minutes) {
      if (minutes === null || minutes === undefined || minutes === "") return "—";
      const value = Number(minutes);
      if (!Number.isFinite(value)) return "—";
      if (Math.abs(value) < 60) return Math.round(value) + " min";
      return (Math.round((value / 60) * 10) / 10).toLocaleString("fr-FR") + " h";
    }
    async function loadCriticalCompliance() {
      const days = $("criticalComplianceDays")?.value || "30";
      const target = $("criticalComplianceTarget")?.value || "30";
      const exam = ($("criticalComplianceExam")?.value || "").trim();
      const unit = ($("criticalComplianceUnit")?.value || "").trim();
      const hint = $("criticalComplianceHint");
      if (hint) hint.textContent = "Chargement du rapport valeurs critiques…";
      try {
        let params = '?days=' + encodeURIComponent(days) + '&target_minutes=' + encodeURIComponent(target);
        if (exam) params += '&exam_code=' + encodeURIComponent(exam);
        if (unit) params += '&unit=' + encodeURIComponent(unit);
        const data = await api('/api/v1/reports/critical-compliance' + params, { headers: headers(false) });
        if ($("critCompTotal")) $("critCompTotal").textContent = data.critical_total ?? 0;
        if ($("critCompHandled")) $("critCompHandled").textContent = (data.ack_rate_pct ?? 0) + "%";
        if ($("critCompLate")) $("critCompLate").textContent = data.critical_late ?? 0;
        if ($("critCompDelay")) $("critCompDelay").textContent = _formatCriticalDelay(data.avg_ack_delay_minutes);
        if (hint) {
          hint.textContent = (data.critical_late || 0) > 0
            ? `${data.critical_late} valeur(s) critique(s) hors délai cible (${data.target_minutes} min), dont ${data.critical_pending || 0} en attente.`
            : `Toutes les valeurs critiques de la période sont dans le délai cible (${data.target_minutes} min).`;
        }
        const summary = data.summary || {};
        const topExams = (summary.top_exams || []).slice(0, 3).map((item) =>
          `${item.label}: ${item.late}/${item.total} hors délai`
        ).join(" · ") || "Aucun examen à signaler";
        const byUnit = (summary.by_unit || []).slice(0, 3).map((item) =>
          `${item.label}: ${item.pending} attente(s)`
        ).join(" · ") || "Aucune unité à signaler";
        if ($("criticalComplianceSummary")) {
          $("criticalComplianceSummary").innerHTML =
            '<strong>Synthèse qualité.</strong> ' + security.escapeHtml(summary.message || "Aucune donnée.") +
            '<br><span style="color:var(--muted);">Examens: ' + security.escapeHtml(topExams) +
            ' · Unités: ' + security.escapeHtml(byUnit) + '</span>';
        }
        const rows = (data.rows || []).map((item) => {
          const status = item.status === "pris_en_charge"
            ? '<span class="pill ok">Prise en charge</span>'
            : '<span class="pill bad">En attente</span>';
          const compliance = item.compliance_status === "dans_delai"
            ? '<span class="pill ok">Dans délai</span>'
            : item.compliance_status === "hors_delai"
              ? '<span class="pill bad">Hors délai</span>'
              : '<span style="color:var(--muted);font-size:11px;">Non mesurable</span>';
          return row(
            '<td><strong>#' + security.escapeHtml(item.result_id) + '</strong></td>' +
            '<td>' + security.escapeHtml(item.patient_name || "—") + '<div class="result-staleness">' + security.escapeHtml(item.patient_ipp || "IPP non renseigné") + '</div></td>' +
            '<td>' + security.escapeHtml(item.sample_barcode || "—") + '</td>' +
            '<td>' + security.escapeHtml(item.exam_code || "—") + '<div class="result-staleness">' + security.escapeHtml(_formatResultDate(item.analysis_date)) + '</div></td>' +
            '<td>' + status + (item.critical_ack_at ? '<div class="result-staleness">' + security.escapeHtml(_formatResultDate(item.critical_ack_at)) + '</div>' : '') + '</td>' +
            '<td>' + security.escapeHtml(item.ack_by || "—") + '</td>' +
            '<td>' + compliance + '</td>' +
            '<td>' + security.escapeHtml(_formatCriticalDelay(item.ack_delay_minutes ?? item.elapsed_minutes)) + '</td>'
          );
        });
        setRows("criticalComplianceTable", rows);
      } catch (e) {
        if (hint) hint.textContent = "Rapport valeurs critiques indisponible.";
        if ($("criticalComplianceSummary")) $("criticalComplianceSummary").textContent = "Synthèse qualité indisponible.";
        setRows("criticalComplianceTable", []);
        log('loadCriticalCompliance: ' + (e.message || e));
      }
    }
    let _criticalComplianceTimer = null;
    function debouncedCriticalComplianceLoad() {
      clearTimeout(_criticalComplianceTimer);
      _criticalComplianceTimer = setTimeout(loadCriticalCompliance, 350);
    }
    async function exportCriticalComplianceCsv() {
      const days = $("criticalComplianceDays")?.value || "30";
      const target = $("criticalComplianceTarget")?.value || "30";
      const exam = ($("criticalComplianceExam")?.value || "").trim();
      const unit = ($("criticalComplianceUnit")?.value || "").trim();
      try {
        let params = '?days=' + encodeURIComponent(days) + '&target_minutes=' + encodeURIComponent(target);
        if (exam) params += '&exam_code=' + encodeURIComponent(exam);
        if (unit) params += '&unit=' + encodeURIComponent(unit);
        const resp = await fetch(normalizeApiPath('/api/v1/reports/critical-compliance/export.csv' + params), { headers: headers(false) });
        if (!resp.ok) { showToast("Export valeurs critiques indisponible", "error"); return; }
        const blob = await resp.blob();
        const url = URL.createObjectURL(blob);
        const a = document.createElement("a");
        a.href = url;
        a.download = "ruggylab-valeurs-critiques-conformite.csv";
        a.click();
        URL.revokeObjectURL(url);
        showToast("Export conformité valeurs critiques généré", "success");
      } catch {
        showToast("Erreur export conformité valeurs critiques", "error");
      }
    }

    // ── Unification des vocabulaires (mappings de codes) ──────────────────────
    let _codeMappings = [];
    async function loadCodeMappings() {
      try {
        _codeMappings = await api('/api/v1/code-mappings', { headers: headers(false) });
        renderMappingsTable();
        loadMappingOrphans();
      } catch (e) { log('loadCodeMappings: ' + (e.message || e)); }
    }
    function renderMappingsTable() {
      const f = ($('mapFilter')?.value || '').trim().toUpperCase();
      const rows = _codeMappings.filter(m => !f || (m.canonical_code + (m.exam_code||'') + (m.test_code||'') + (m.analyte_code||'')).toUpperCase().includes(f));
      setRows('mappingsTable', rows.map(m => row(
        `<td><strong>${security.escapeHtml(m.canonical_code)}</strong>${m.component_of ? ` <small style="color:var(--muted);">∈${security.escapeHtml(m.component_of)}</small>` : ''}</td>` +
        `<td>${security.escapeHtml(m.exam_code || '—')}</td>` +
        `<td>${security.escapeHtml(m.test_code || '—')}</td>` +
        `<td>${security.escapeHtml(m.analyte_code || '—')}</td>` +
        `<td>${m.is_panel ? '✔' : ''}</td>` +
        `<td><button class="ghost" style="color:var(--rose);font-size:11px;" onclick="deleteMapping(${m.id},this)">✕</button></td>`
      )));
    }
    async function loadMappingOrphans() {
      try {
        const o = await api('/api/v1/code-mappings/orphans', { headers: headers(false) });
        const ex = o.exam_codes_unmapped || [], te = o.test_codes_unmapped || [];
        $('mapOrphans').innerHTML =
          `<strong>Codes orphelins</strong> — exam (${ex.length}) : ${ex.slice(0,20).map(security.escapeHtml).join(', ') || '—'}` +
          `<br>test (${te.length}) : ${te.slice(0,20).map(security.escapeHtml).join(', ') || '—'}`;
      } catch {}
    }
    async function seedCodeMappings(btn) {
      setLoading(btn, true);
      try {
        const res = await api('/api/v1/code-mappings/seed-defaults', { method: 'POST', headers: headers() });
        showToast(`${res.created} correspondance(s) chargée(s)`, 'success');
        await loadCodeMappings();
      } catch (e) { showToast('Erreur (officier requis ?)', 'error'); }
      finally { setLoading(btn, false); }
    }
    async function deleteMapping(id, btn) {
      setLoading(btn, true);
      try { await api(`/api/v1/code-mappings/${id}`, { method: 'DELETE', headers: headers() }); showToast('Correspondance désactivée', 'success'); loadCodeMappings(); }
      catch { showToast('Erreur suppression', 'error'); }
      finally { setLoading(btn, false); }
    }
    async function testMapping(btn) {
      const exam_code = ($('mapTestExam')?.value || '').trim().toUpperCase();
      const analyte_code = ($('mapTestAnalyte')?.value || '').trim().toUpperCase() || null;
      if (!exam_code) { showToast('Saisir un exam_code', 'error'); return; }
      setLoading(btn, true);
      try {
        const d = await api('/api/v1/code-mappings/test', { method: 'POST', headers: headers(), body: JSON.stringify({ exam_code, analyte_code }) });
        $('mapTestResult').innerHTML = d.matched
          ? `<div class="notice">✅ <strong>${security.escapeHtml(exam_code)}</strong>${analyte_code ? ' / ' + security.escapeHtml(analyte_code) : ''} → canonique <strong>${security.escapeHtml(d.canonical_code || '—')}</strong>, bioref <strong>${security.escapeHtml(d.bioref_test_code || '—')}</strong>${d.is_panel ? ' (panel)' : ''}</div>`
          : `<div class="notice" style="color:var(--rose);">Aucune correspondance pour « ${security.escapeHtml(exam_code)} »</div>`;
      } catch (e) { showToast('Erreur test mapping', 'error'); }
      finally { setLoading(btn, false); }
    }

    // ── Référentiel biologique & interprétation ───────────────────────────────
    let _biorefRanges = [];
    async function loadBioref() {
      try {
        _biorefRanges = await api('/api/v1/bioref/ranges', { headers: headers(false) });
        const sel = $('biorefTest');
        if (sel) {
          const codes = [];
          const seen = new Set();
          _biorefRanges.forEach(r => { if (!seen.has(r.test_code)) { seen.add(r.test_code); codes.push(r); } });
          const cur = sel.value;
          sel.innerHTML = codes.map(r => `<option value="${security.escapeHtml(r.test_code)}">${security.escapeHtml(r.test_code)} — ${security.escapeHtml(r.test_name)}</option>`).join('');
          if (cur) sel.value = cur;
        }
        renderBiorefTable();
      } catch (e) { log('loadBioref: ' + (e.message || e)); }
    }
    function _biorefRangeStr(r) {
      if (r.normal_text) return r.normal_text;
      const u = r.unit || '';
      if (r.lower_limit != null && r.upper_limit != null) return `${r.lower_limit} - ${r.upper_limit} ${u}`.trim();
      if (r.upper_limit != null) return `< ${r.upper_limit} ${u}`.trim();
      if (r.lower_limit != null) return `> ${r.lower_limit} ${u}`.trim();
      return u || '—';
    }
    function renderBiorefTable() {
      const f = ($('biorefFilter')?.value || '').trim().toUpperCase();
      const rows = _biorefRanges.filter(r => !f || r.test_code.toUpperCase().includes(f));
      setRows('biorefTable', rows.map(r => row(
        `<td><strong>${security.escapeHtml(r.test_code)}</strong></td>` +
        `<td>${security.escapeHtml(r.test_name)}</td>` +
        `<td>${security.escapeHtml(r.sex)}</td>` +
        `<td>${security.escapeHtml(_biorefRangeStr(r))}</td>` +
        `<td style="font-size:11px;color:var(--muted);">${security.escapeHtml(r.source || '')}</td>`
      )));
    }
    async function seedBioref(btn) {
      setLoading(btn, true);
      try {
        const res = await api('/api/v1/bioref/seed-defaults', { method: 'POST', headers: headers() });
        showToast(`${res.created} valeur(s) de référence chargée(s)`, 'success');
        await loadBioref();
      } catch (e) { showToast('Erreur (officier requis ?)', 'error'); }
      finally { setLoading(btn, false); }
    }
    const _biorefFlagBadge = (f) => {
      if (f === 'NORMAL') return '<span class="pill ok">NORMAL</span>';
      if (f === 'BAS' || f === 'HAUT') return `<span class="pill" style="background:var(--amber);color:#fff;">${f}</span>`;
      if (f && f.startsWith('CRITIQUE')) return `<span class="pill bad">${f}</span>`;
      return `<span class="pill">${security.escapeHtml(f || '—')}</span>`;
    };
    async function interpretBioref(btn) {
      const test_code = $('biorefTest')?.value;
      if (!test_code) { showToast('Sélectionnez un test (chargez le référentiel)', 'error'); return; }
      const vRaw = $('biorefValue').value;
      const body = {
        test_code,
        value: vRaw === '' ? null : Number(vRaw),
        sex: $('biorefSex').value || null,
        age_years: $('biorefAge').value === '' ? null : Number($('biorefAge').value),
      };
      setLoading(btn, true);
      try {
        const d = await api('/api/v1/bioref/interpret', { method: 'POST', headers: headers(), body: JSON.stringify(body) });
        if (d.error) { $('biorefResult').innerHTML = `<div class="notice" style="color:var(--rose);">${security.escapeHtml(d.error)}</div>`; return; }
        $('biorefResult').innerHTML =
          `<div class="panel" style="padding:10px;">` +
          `<div style="display:flex;justify-content:space-between;align-items:center;">` +
            `<strong>${security.escapeHtml(d.test_name)}</strong> ${_biorefFlagBadge(d.flag)}</div>` +
          `<div style="margin-top:6px;font-size:13px;">Résultat : <strong>${d.result ?? '—'} ${security.escapeHtml(d.unit || '')}</strong> ` +
            `· Référence : ${security.escapeHtml(d.reference_range || '—')}</div>` +
          (d.interpretation ? `<div style="margin-top:4px;font-size:12px;color:var(--muted);">${security.escapeHtml(d.interpretation)}</div>` : '') +
          (d.source ? `<div style="margin-top:2px;font-size:11px;color:var(--muted);">Source : ${security.escapeHtml(d.source)}</div>` : '') +
          `</div>`;
      } catch (e) { showToast('Erreur interprétation', 'error'); }
      finally { setLoading(btn, false); }
    }

    // ── Auto-validation ISO 15189 §5.8 ────────────────────────────────────────
    async function loadAutoValidationConfigs() {
      try {
        const data = await api("/api/v1/auto-validation/config", { headers: headers(false) });
        setRows("autoValidConfigTable", data.map(c => row(
          `<td><strong>${security.escapeHtml(c.name)}</strong></td>` +
          `<td>${c.require_all_flags_normal ? '✅' : '—'}</td>` +
          `<td>${c.require_no_delta ? '✅' : '—'}</td>` +
          `<td>${c.require_not_critical ? '✅' : '—'}</td>` +
          `<td><button class="ghost" style="color:var(--rose);font-size:11px;" onclick="deleteAutoValidationConfig(${c.id}, this)">Supprimer</button></td>`
        )));
      } catch (e) { log('loadAutoValidationConfigs: ' + (e.message || e)); }
    }
    async function createAutoValidationConfig(btn) {
      setLoading(btn, true);
      try {
        await api("/api/v1/auto-validation/config", {
          method: "POST", headers: headers(),
          body: JSON.stringify({
            name: $('avName').value || 'Règle par défaut',
            require_all_flags_normal: $('avFlagsNormal').checked,
            require_no_delta: $('avNoDelta').checked,
            require_not_critical: $('avNotCritical').checked,
          }),
        });
        showToast("Règle d'auto-validation créée", "success");
        await loadAutoValidationConfigs();
      } catch (e) { showToast("Erreur création règle", "error"); }
      finally { setLoading(btn, false); }
    }
    async function deleteAutoValidationConfig(id, btn) {
      setLoading(btn, true);
      try {
        await api("/api/v1/auto-validation/config/" + id, { method: "DELETE", headers: headers() });
        showToast("Règle désactivée", "success");
        await loadAutoValidationConfigs();
      } catch (e) { showToast("Erreur suppression règle", "error"); }
      finally { setLoading(btn, false); }
    }
    async function runAutoValidation(btn) {
      setLoading(btn, true);
      try {
        const res = await api("/api/v1/auto-validation/run", { method: "POST", headers: headers() });
        showToast(`Auto-validation : ${res.auto_validated}/${res.processed} résultat(s) validé(s)`, "success");
        await loadResults();
      } catch (e) { showToast("Erreur auto-validation", "error"); }
      finally { setLoading(btn, false); }
    }

    // ── Correction / ré-analyse résultat ─────────────────────────────────────
    function openAmendPanel(resultId, dataPoints) {
      $('amendResultId').value = resultId;
      $('amendResultLabel').textContent = 'Résultat #' + resultId;
      $('amendDataPoints').value = JSON.stringify(dataPoints, null, 2);
      $('amendReason').value = '';
      const panel = $('amendPanel');
      if (panel) { panel.style.display = ''; panel.scrollIntoView({ behavior: 'smooth', block: 'start' }); }
    }
    function closeAmendPanel() {
      const panel = $('amendPanel');
      if (panel) panel.style.display = 'none';
    }
    async function submitAmend(btn) {
      const resultId = $('amendResultId').value;
      const rawJson = $('amendDataPoints').value;
      const reason = ($('amendReason').value || '').trim();
      if (!resultId) { showToast("Aucun résultat sélectionné", "error"); return; }
      if (reason.length < 5) { showToast("Motif trop court (min 5 car.)", "error"); return; }
      let dataPoints;
      try { dataPoints = JSON.parse(rawJson); } catch { showToast("JSON invalide dans les données analytiques", "error"); return; }
      setLoading(btn, true);
      try {
        await api("/api/v1/results/" + resultId + "/amend", {
          method: "PATCH", headers: headers(),
          body: JSON.stringify({ data_points: dataPoints, amendment_reason: reason }),
        });
        showToast("Résultat corrigé avec succès", "success");
        closeAmendPanel();
        await loadResults();
      } catch (e) {
        showToast((e.detail || e.message || "Erreur correction"), "error");
      } finally { setLoading(btn, false); }
    }

    // ── Péremptions réactifs ───────────────────────────────────────────────────
    async function loadExpiryAlerts() {
      const days = parseInt($('expiryDays')?.value || '30', 10);
      try {
        const data = await api(`/api/v1/reagents/expiring?days=${days}`, { headers: headers(false) });
        setRows("expiryTable", data.map(r => {
          const daysLeft = r.days_remaining;
          let badge;
          if (r.is_expired) badge = '<span class="pill bad">Expiré</span>';
          else if (daysLeft <= 7) badge = `<span class="pill bad">${daysLeft}j</span>`;
          else if (daysLeft <= 30) badge = `<span class="pill" style="background:var(--amber);color:#fff;">${daysLeft}j</span>`;
          else badge = `<span class="pill ok">${daysLeft}j</span>`;
          const tr = row(
            `<td><strong>${security.escapeHtml(r.name)}</strong></td>` +
            `<td><code>${security.escapeHtml(r.lot_number || '—')}</code></td>` +
            `<td>${r.expiry_date || '—'}</td>` +
            `<td>${badge}</td>` +
            `<td style="font-variant-numeric:tabular-nums;">${r.current_stock} <small style="color:var(--muted);">${security.escapeHtml(r.unit || '')}</small></td>`
          );
          if (r.is_expired) tr.classList.add('row-critical');
          else if (daysLeft <= 7) tr.classList.add('row-warning');
          return tr;
        }));
      } catch (e) { showToast("Erreur chargement péremptions", "error"); log('loadExpiryAlerts: ' + (e.message || e)); }
    }
    async function notifyExpiryAlerts(btn) {
      const days = parseInt($('expiryDays')?.value || '30', 10);
      setLoading(btn, true);
      try {
        const res = await api(`/api/v1/critical-alerts/expiry-check?days=${days}`, { method: "POST", headers: headers() });
        showToast(`Notifications envoyées : ${res.notified} webhook(s), ${res.expiring} réactif(s) concerné(s)`, "success");
      } catch (e) { showToast("Erreur envoi notifications péremption", "error"); }
      finally { setLoading(btn, false); }
    }

    // ══════════════════════════════════════════════════════════════════════
    //  Feature 2 — Dossier patient complet (timeline + sparklines + FHIR)
    // ══════════════════════════════════════════════════════════════════════
    let _dossierPatientId = null;
    function closeDossier() {
      const d = $('patientDossier');
      if (d) d.style.display = 'none';
      _dossierPatientId = null;
    }
    async function openDossier(patientId) {
      _dossierPatientId = patientId;
      try {
        const h = await api(`/api/v1/patients/${patientId}/history`, { headers: headers(false) });
        const p = h.patient || {};
        $('dossierName').textContent = `${p.first_name || ''} ${p.last_name || ''} — ${p.ipp_unique_id || ''}`;
        $('dossierResults').textContent = h.result_count ?? 0;
        $('dossierCritical').textContent = h.critical_count ?? 0;
        $('dossierSamples').textContent = h.sample_count ?? 0;
        const trends = h.trends || {};
        const analyteKeys = Object.keys(trends);
        $('dossierAnalytes').textContent = analyteKeys.length;

        // Sparklines
        const trendDiv = $('dossierTrends');
        if (trendDiv) {
          if (!analyteKeys.length) {
            trendDiv.innerHTML = '<p style="color:var(--muted);">Aucune donnée numérique.</p>';
          } else {
            trendDiv.innerHTML = analyteKeys.slice(0, 12).map(a => {
              const series = trends[a].map(pt => pt.value);
              const last = series[series.length - 1];
              return `<div style="display:flex;align-items:center;gap:10px;margin-bottom:6px;">` +
                `<span style="width:80px;font-size:12px;font-weight:600;">${security.escapeHtml(a)}</span>` +
                _renderSparkline(series) +
                `<span style="font-size:12px;color:var(--muted);">${last} <small>(n=${series.length})</small></span>` +
                `</div>`;
            }).join('');
          }
        }

        // Timeline
        setRows('dossierTimeline', (h.timeline || []).map(t => {
          const flagsTxt = t.flags && Object.keys(t.flags).length
            ? Object.entries(t.flags).map(([k, v]) => `${k}:${v}`).join(' ')
            : '—';
          const crit = t.is_critical ? '<span class="pill bad">⛔</span>' : (t.delta_exceeded ? '<span class="pill" style="background:var(--amber);color:#fff;">△</span>' : '—');
          const tr = row(
            `<td>${t.result_id}</td>` +
            `<td style="white-space:nowrap;">${t.analysis_date ? new Date(t.analysis_date).toLocaleString('fr-FR',{dateStyle:'short',timeStyle:'short'}) : '—'}</td>` +
            `<td><code>${security.escapeHtml(t.sample_barcode || '')}</code></td>` +
            `<td>${crit}</td>` +
            `<td style="font-size:11px;">${security.escapeHtml(flagsTxt)}</td>`
          );
          if (t.is_critical) tr.classList.add('row-critical');
          return tr;
        }));

        const dossier = $('patientDossier');
        if (dossier) { dossier.style.display = ''; dossier.scrollIntoView({ behavior: 'smooth', block: 'start' }); }
      } catch (e) {
        showToast('Erreur chargement dossier', 'error');
        log('openDossier: ' + (e.message || e));
      }
    }
    function _renderSparkline(values) {
      if (!values.length) return '<svg width="120" height="28"></svg>';
      const W = 120, H = 28, pad = 2;
      const min = Math.min(...values), max = Math.max(...values);
      const span = (max - min) || 1;
      const step = values.length > 1 ? (W - 2 * pad) / (values.length - 1) : 0;
      const pts = values.map((v, i) => {
        const x = pad + i * step;
        const y = H - pad - ((v - min) / span) * (H - 2 * pad);
        return `${x.toFixed(1)},${y.toFixed(1)}`;
      }).join(' ');
      const lastX = pad + (values.length - 1) * step;
      const lastY = H - pad - ((values[values.length - 1] - min) / span) * (H - 2 * pad);
      return `<svg width="${W}" height="${H}" style="overflow:visible;">` +
        `<polyline points="${pts}" fill="none" stroke="#2563eb" stroke-width="1.5"/>` +
        `<circle cx="${lastX.toFixed(1)}" cy="${lastY.toFixed(1)}" r="2.5" fill="#be123c"/>` +
        `</svg>`;
    }
    async function editPatientUnit() {
      if (!_dossierPatientId) return;
      const value = prompt("Unité / service de rattachement (laisser vide = pool partagé) :");
      if (value === null) return;  // annulé
      const unit = value.trim() || null;
      try {
        await api(`/api/v1/patients/${_dossierPatientId}`, {
          method: "PATCH", headers: headers(), body: JSON.stringify({ unit }),
        });
        showToast("Unité du patient mise à jour", "success");
        loadPatients();
      } catch (e) {
        showToast(e.message === "Forbidden" ? "Réservé officier/admin" : "Erreur mise à jour", "error");
      }
    }
    async function exportPatientFhir() {
      if (!_dossierPatientId) return;
      try {
        const resp = await fetch(normalizeApiPath(`/api/v1/patients/${_dossierPatientId}/fhir-bundle`), { headers: headers(false) });
        if (!resp.ok) { showToast('Export FHIR refusé', 'error'); return; }
        const blob = await resp.blob();
        const url = URL.createObjectURL(blob);
        const a = document.createElement('a');
        a.href = url; a.download = `patient-${_dossierPatientId}-fhir-bundle.json`; a.click();
        URL.revokeObjectURL(url);
        showToast('Bundle FHIR téléchargé', 'success');
      } catch { showToast('Erreur export FHIR', 'error'); }
    }

    // ══════════════════════════════════════════════════════════════════════
    //  Feature 3 — Notifications temps-réel (WebSocket + fallback polling)
    // ══════════════════════════════════════════════════════════════════════
    var _notifWs = null;
    var _notifPollTimer = null;
    var _lastCriticalCount = 0;
    var _notifPopoverOpen = false;

    function toggleNotifPopover() {
      _notifPopoverOpen = !_notifPopoverOpen;
      const pop = $('notifPopover');
      if (pop) pop.style.display = _notifPopoverOpen ? 'block' : 'none';
    }
    function _setNotifWsDot(connected) {
      const dot = $('notifWsDot');
      if (!dot) return;
      dot.style.background = connected ? 'var(--teal, #0f766e)' : 'var(--muted)';
      dot.title = connected ? 'WebSocket connecté' : 'WebSocket déconnecté (polling)';
    }
    function renderNotifSnapshot(snap) {
      if (!snap) return;
      const total = snap.total || 0;
      const badge = $('notifBadge');
      if (badge) {
        badge.textContent = total;
        badge.style.display = total > 0 ? '' : 'none';
      }
      // Toast si nouvelle valeur critique apparaît
      const critCount = (snap.counts && snap.counts.criticals) || 0;
      if (critCount > _lastCriticalCount) {
        showToast(`🔴 ${critCount} valeur(s) critique(s) à prendre en charge`, 'error', 6000);
      }
      _lastCriticalCount = critCount;

      const body = $('notifPopoverBody');
      if (!body) return;
      if (total === 0) { body.innerHTML = '<p style="color:var(--muted);">Aucune alerte active. ✅</p>'; return; }
      const c = snap.counts || {};
      let html = '<div style="display:flex;gap:6px;flex-wrap:wrap;margin-bottom:10px;">';
      if (c.criticals) html += `<span class="pill bad">⛔ ${c.criticals} critiques</span>`;
      if (c.deltas) html += `<span class="pill" style="background:var(--amber);color:#fff;">△ ${c.deltas} delta</span>`;
      if (c.expiring) html += `<span class="pill" style="background:#b45309;color:#fff;">📅 ${c.expiring} péremptions</span>`;
      if (c.qc_rejects) html += `<span class="pill bad">📈 ${c.qc_rejects} QC rejet</span>`;
      html += '</div>';
      if ((snap.criticals || []).length) {
        html += '<strong style="font-size:12px;">Valeurs critiques :</strong><ul style="margin:4px 0 8px;padding-left:18px;">';
        snap.criticals.slice(0, 6).forEach(x => {
          html += `<li>Résultat #${x.result_id} (échantillon ${x.sample_id}) — ${x.elapsed_minutes} min${x.overdue ? ' <span class="pill bad" style="font-size:9px;">retard</span>' : ''}</li>`;
        });
        html += '</ul>';
      }
      if ((snap.expiring || []).length) {
        html += '<strong style="font-size:12px;">Péremptions proches :</strong><ul style="margin:4px 0 8px;padding-left:18px;">';
        snap.expiring.slice(0, 6).forEach(x => {
          html += `<li>${security.escapeHtml(x.name)} — ${x.is_expired ? 'expiré' : x.days_remaining + 'j'}</li>`;
        });
        html += '</ul>';
      }
      body.innerHTML = html;
    }
    function connectNotifications() {
      if (!token) return;
      // Tente WebSocket d'abord. Le jeton transite par le sous-protocole
      // (et non l'URL) pour éviter de le journaliser côté serveur/proxy.
      try {
        const proto = location.protocol === 'https:' ? 'wss' : 'ws';
        const ws = new WebSocket(`${proto}://${location.host}${API_PREFIX}/notifications/ws`, ['bearer', token]);
        _notifWs = ws;
        ws.onopen = () => { _setNotifWsDot(true); if (_notifPollTimer) { clearInterval(_notifPollTimer); _notifPollTimer = null; } };
        ws.onmessage = (ev) => { try { renderNotifSnapshot(JSON.parse(ev.data)); } catch {} };
        ws.onclose = () => { _setNotifWsDot(false); _notifWs = null; startNotifPolling(); };
        ws.onerror = () => { try { ws.close(); } catch {} };
      } catch {
        startNotifPolling();
      }
    }
    function startNotifPolling() {
      if (_notifPollTimer) return;
      const poll = async () => {
        if (!token) return;
        try { renderNotifSnapshot(await api('/api/v1/notifications/feed', { headers: headers(false) })); } catch {}
      };
      poll();
      _notifPollTimer = setInterval(poll, 30000);
    }
    function disconnectNotifications() {
      if (_notifWs) { try { _notifWs.close(); } catch {} _notifWs = null; }
      if (_notifPollTimer) { clearInterval(_notifPollTimer); _notifPollTimer = null; }
    }

    // ══════════════════════════════════════════════════════════════════════
    //  Feature 4 — Import en lot CSV
    // ══════════════════════════════════════════════════════════════════════
    function loadCsvIntoTextarea(input, textareaId) {
      const file = input.files && input.files[0];
      if (!file) return;
      const reader = new FileReader();
      reader.onload = () => { const ta = $(textareaId); if (ta) ta.value = reader.result; };
      reader.readAsText(file);
    }
    function fillPatientCsvSample() {
      $('patientCsvText').value =
        'ipp_unique_id,first_name,last_name,birth_date,sex,rank\n' +
        'IPP-IMP-001,Awa,Koné,1990-05-12,F,Sergent\n' +
        'IPP-IMP-002,Yao,Brou,1985-11-03,M,Caporal';
    }
    function fillReagentCsvSample() {
      $('reagentCsvText').value =
        'name,category,unit,current_stock,alert_threshold,lot_number,expiry_date,supplier\n' +
        'Diluant DH36 (import),Hématologie,L,20,5,LOT-IMP-A1,2027-01-01,Sysmex\n' +
        'Lyse WBC (import),Hématologie,mL,500,100,LOT-IMP-B2,2026-09-30,Sysmex';
    }
    async function submitBulkImport(kind, btn) {
      const taId = kind === 'patients' ? 'patientCsvText' : 'reagentCsvText';
      const reportId = kind === 'patients' ? 'patientImportReport' : 'reagentImportReport';
      const dryRunId = kind === 'patients' ? 'patientCsvDryRun' : 'reagentCsvDryRun';
      const csv = ($(taId)?.value || '').trim();
      const dryRun = !!$(dryRunId)?.checked;
      if (!csv) { showToast('CSV vide', 'error'); return; }
      setLoading(btn, true);
      try {
        const res = await api(`/api/v1/bulk-import/${kind}`, {
          method: 'POST', headers: headers(), body: JSON.stringify({ csv, dry_run: dryRun }),
        });
        const verb = res.dry_run ? 'validable(s) (dry-run, rien enregistré)' : 'créé(s)';
        let html = `<div class="notice">✅ ${res.created} ${verb} sur ${res.total} ligne(s).</div>`;
        if (res.errors && res.errors.length) {
          html += '<div style="margin-top:6px;color:var(--rose);"><strong>Erreurs :</strong><ul style="margin:4px 0;padding-left:18px;">';
          res.errors.slice(0, 30).forEach(e => { html += `<li>Ligne ${e.row} : ${security.escapeHtml(e.error)}</li>`; });
          html += '</ul></div>';
        }
        $(reportId).innerHTML = html;
        showToast(`${res.created} ${kind === 'patients' ? 'patient(s)' : 'réactif(s)'} ${res.dry_run ? 'validé(s) à blanc' : 'importé(s)'}`, 'success');
        if (!res.dry_run) { if (kind === 'patients') loadPatients(); else { loadReagents(); loadExpiryAlerts(); } }
      } catch (e) {
        showToast('Erreur import (droits officier requis ?)', 'error');
        log('submitBulkImport: ' + (e.message || e));
      } finally { setLoading(btn, false); }
    }

    // ══════════════════════════════════════════════════════════════════════
    //  Registre maître — analyse rétrospective & import
    // ══════════════════════════════════════════════════════════════════════
    // Parseur CSV conforme RFC 4180 (gère les champs entre guillemets contenant
    // des virgules — indispensable car les examens ont des décimales « 0,13 »).
    function _parseCsv(text) {
      const rows = [];
      let row = [], field = '', inQuotes = false;
      for (let i = 0; i < text.length; i++) {
        const c = text[i];
        if (inQuotes) {
          if (c === '"') {
            if (text[i + 1] === '"') { field += '"'; i++; }
            else inQuotes = false;
          } else field += c;
        } else if (c === '"') inQuotes = true;
        else if (c === ',') { row.push(field); field = ''; }
        else if (c === '\r') { /* ignore */ }
        else if (c === '\n') { row.push(field); rows.push(row); row = []; field = ''; }
        else field += c;
      }
      if (field !== '' || row.length) { row.push(field); rows.push(row); }
      return rows.filter(r => r.some(v => v.trim() !== ''));
    }
    function _registreRows() {
      const text = ($('registreCsvText')?.value || '').trim();
      if (!text) return [];
      const grid = _parseCsv(text);
      if (grid.length < 2) return [];
      const headers = grid[0].map(h => h.trim());
      return grid.slice(1).map(cells => {
        const obj = {};
        headers.forEach((h, i) => { obj[h] = (cells[i] ?? '').trim(); });
        return obj;
      });
    }
    function _fmtFcfa(n) { return (n || 0).toLocaleString('fr-FR') + ' F'; }

    async function registreAnalyse(btn) {
      const rows = _registreRows();
      if (!rows.length) { showToast('CSV vide ou en-tête manquante', 'error'); return; }
      setLoading(btn, true);
      try {
        const a = await api('/api/v1/registre/analytics', { method: 'POST', headers: headers(), body: JSON.stringify({ rows }) });
        $('registreAnalyticsPanel').style.display = '';
        $('regTotal').textContent = a.total_dossiers;
        $('regRevenue').textContent = _fmtFcfa(a.revenue_total_fcfa);
        $('regCmu').textContent = _fmtFcfa(a.cmu_part_fcfa) + ` (${a.cmu_share_pct}%)`;
        $('regMalaria').textContent = `${a.malaria_positivity_pct}% (${a.malaria_positive}/${a.malaria_tested})`;
        setRows('regTopExams', a.top_exams.map(([name, n]) => row(`<td>${security.escapeHtml(name)}</td><td>${n}</td>`)));
        _renderRegMonthChart(a.by_month);
        showToast('Analyse calculée', 'success');
      } catch (e) { showToast('Erreur analyse', 'error'); log('registreAnalyse: ' + (e.message || e)); }
      finally { setLoading(btn, false); }
    }

    function _renderRegMonthChart(months) {
      const div = $('regMonthChart');
      if (!div) return;
      if (!months || !months.length) { div.innerHTML = '<p style="color:var(--muted);">Aucune date exploitable.</p>'; return; }
      const maxV = Math.max(...months.map(m => m.count), 1);
      const W = 460, H = 150, padTop = 14, padBot = 26, padL = 4;
      const cw = W - padL * 2, ch = H - padTop - padBot;
      const bw = Math.max(4, Math.floor(cw / months.length) - 4);
      let bars = '';
      months.forEach((m, i) => {
        const x = padL + i * (cw / months.length) + 2;
        const bh = Math.max(2, Math.round((m.count / maxV) * ch));
        const y = padTop + ch - bh;
        bars += `<rect x="${x}" y="${y}" width="${bw}" height="${bh}" rx="3" fill="#0f766e" opacity="0.8"><title>${m.month}: ${m.count} dossiers</title></rect>` +
          `<text x="${x + bw / 2}" y="${H - 8}" text-anchor="middle" font-size="8" fill="var(--muted)">${m.month.slice(2)}</text>`;
      });
      div.innerHTML = `<svg viewBox="0 0 ${W} ${H}" width="100%" style="overflow:visible;display:block;">${bars}</svg>`;
    }

    function _renderRegReport(rep) {
      $('registreReportPanel').style.display = '';
      let html = '';
      if ('recognition_rate_pct' in rep) {
        html += `<div class="notice">Prévisualisation : ${rep.total_rows} dossier(s), ${rep.total_exams} examen(s), ` +
          `<strong>${rep.recognized_exams} reconnus (${rep.recognition_rate_pct}%)</strong>, ${rep.unrecognized_exams} non reconnus. ` +
          `Montant total : ${_fmtFcfa(rep.total_amount_fcfa)}.</div>`;
        if (rep.top_unrecognized && rep.top_unrecognized.length) {
          html += '<p style="font-size:12px;"><strong>Examens non reconnus :</strong> ' +
            rep.top_unrecognized.map(([n, c]) => `${security.escapeHtml(n)} (${c})`).join(', ') + '</p>';
        }
      } else {
        const mode = rep.dry_run ? 'Simulation (rien écrit)' : '✅ Import réel effectué';
        html += `<div class="notice">${mode} : ${rep.created_patients} patient(s), ${rep.created_samples} échantillon(s), ` +
          `${rep.created_results} résultat(s). Dates de naissance estimées : ${rep.estimated_birth_dates}.</div>`;
      }
      if (rep.errors && rep.errors.length) {
        html += '<div style="color:var(--rose);margin-top:6px;"><strong>Erreurs :</strong><ul style="margin:4px 0;padding-left:18px;">' +
          rep.errors.slice(0, 30).map(e => `<li>Ligne ${e.row} : ${security.escapeHtml(e.error)}</li>`).join('') + '</ul></div>';
      }
      $('registreReport').innerHTML = html;
    }

    async function registrePreview(btn) {
      const rows = _registreRows();
      if (!rows.length) { showToast('CSV vide ou en-tête manquante', 'error'); return; }
      setLoading(btn, true);
      try {
        const rep = await api('/api/v1/registre/preview', { method: 'POST', headers: headers(), body: JSON.stringify({ rows }) });
        _renderRegReport(rep);
        showToast('Prévisualisation prête', 'success');
      } catch (e) { showToast('Erreur prévisualisation', 'error'); }
      finally { setLoading(btn, false); }
    }

    async function registreImport(btn) {
      const rows = _registreRows();
      if (!rows.length) { showToast('CSV vide ou en-tête manquante', 'error'); return; }
      if (!confirm(`Importer réellement ${rows.length} dossier(s) en base ? Cette action écrit des données patients.`)) return;
      setLoading(btn, true);
      try {
        const rep = await api('/api/v1/registre/import', { method: 'POST', headers: headers(), body: JSON.stringify({ rows, dry_run: false, confirm: true }) });
        _renderRegReport(rep);
        showToast(`Import : ${rep.created_patients} patient(s) créé(s)`, 'success');
      } catch (e) { showToast(e.message === 'Forbidden' ? 'Réservé officier/admin' : 'Erreur import', 'error'); }
      finally { setLoading(btn, false); }
    }

    // ══════════════════════════════════════════════════════════════════════
    //  Suivi TAT — Performance laboratoire
    // ══════════════════════════════════════════════════════════════════════
    const _tatStatusBadge = (s) => ({
      green: '<span class="pill ok">Dans les délais</span>',
      orange: '<span class="pill" style="background:var(--amber);color:#fff;">Retard modéré</span>',
      red: '<span class="pill bad">Retard important</span>',
      unknown: '<span class="pill" style="background:var(--muted);color:#fff;">N/A</span>',
    }[s] || s);

    function _fmtTat(min) {
      if (min === null || min === undefined) return '—';
      if (min < 60) return `${min} min`;
      const h = Math.floor(min / 60), m = Math.round(min % 60);
      return m ? `${h}h${String(m).padStart(2, '0')}` : `${h}h`;
    }

    async function loadTat() {
      const days = $('tatDays')?.value || '30';
      try {
        const [dash, targets, alerts] = await Promise.all([
          api(`/api/v1/tat/dashboard?days=${days}`, { headers: headers(false) }),
          api('/api/v1/tat/targets', { headers: headers(false) }),
          api(`/api/v1/tat/alerts?days=${Math.min(Number(days), 90)}`, { headers: headers(false) }).catch(() => []),
        ]);
        $('tatMeasured').textContent = dash.total_measured;
        $('tatOnTime').textContent = dash.on_time_pct + '%';
        $('tatLate').textContent = dash.late_count;
        $('tatAlerts').textContent = alerts.length;
        const otp = $('tatOnTimePanel');
        if (otp) { otp.classList.remove('metric-teal', 'metric-amber', 'metric-rose'); otp.classList.add(dash.on_time_pct >= 90 ? 'metric-teal' : dash.on_time_pct >= 75 ? 'metric-amber' : 'metric-rose'); }
        const lp = $('tatLatePanel');
        if (lp) { lp.classList.remove('metric-teal', 'metric-rose'); lp.classList.add(dash.late_count > 0 ? 'metric-rose' : 'metric-teal'); }

        setRows('tatTargetsTable', targets.map(t => row(
          `<td><strong>${security.escapeHtml(t.exam_code)}</strong></td>` +
          `<td>${security.escapeHtml(t.label)}</td>` +
          `<td>${_fmtTat(t.target_minutes)}</td>` +
          `<td>${_fmtTat(Math.round(t.target_minutes * t.warn_factor))}</td>` +
          `<td><button class="ghost" style="color:var(--rose);font-size:11px;" onclick="deleteTatTarget(${t.id},this)">Supprimer</button></td>`
        )));

        setRows('tatAlertsTable', alerts.map(a => {
          const tr = row(
            `<td>#${a.result_id}</td>` +
            `<td>${security.escapeHtml(a.exam_code || '—')}</td>` +
            `<td>${_fmtTat(a.total_minutes)}</td>` +
            `<td>${_fmtTat(a.target_minutes)}</td>` +
            `<td>${_tatStatusBadge(a.status)}</td>`
          );
          tr.classList.add(a.status === 'red' ? 'row-critical' : 'row-warning');
          return tr;
        }));

        setRows('tatByExamTable', dash.by_exam.map(e => row(
          `<td><strong>${security.escapeHtml(e.label || e.exam_code)}</strong></td>` +
          `<td>${e.count}</td>` +
          `<td>${_fmtTat(e.mean_min)}</td>` +
          `<td>${_fmtTat(e.max_min)}</td>` +
          `<td>${e.on_time_pct === null || e.on_time_pct === undefined ? '—' : e.on_time_pct + '%'}</td>` +
          `<td>${e.late_count}</td>`
        )));
        setRows('tatByTechTable', dash.by_technician.map(t => row(
          `<td>${security.escapeHtml(t.technician)}</td><td>${t.count}</td><td>${_fmtTat(t.mean_min)}</td><td>${_fmtTat(t.max_min)}</td>`
        )));
        setRows('tatByAutoTable', dash.by_automate.map(t => row(
          `<td>${security.escapeHtml(t.automate)}</td><td>${t.count}</td><td>${_fmtTat(t.mean_min)}</td><td>${_fmtTat(t.max_min)}</td>`
        )));
        _renderTatByDayChart(dash.by_day);
      } catch (e) { showToast('Erreur chargement TAT', 'error'); log('loadTat: ' + (e.message || e)); }
    }

    function _renderTatByDayChart(days) {
      const div = $('tatByDayChart');
      if (!div) return;
      if (!days || !days.length) { div.innerHTML = '<p style="color:var(--muted);text-align:center;padding:24px 0;">Aucune donnée.</p>'; return; }
      const maxV = Math.max(...days.map(d => d.mean_min), 1);
      const W = 460, H = 160, padTop = 16, padBot = 28, padL = 4;
      const chartW = W - padL * 2, chartH = H - padTop - padBot;
      const bw = Math.max(4, Math.floor(chartW / days.length) - 4);
      let bars = '';
      days.forEach((d, i) => {
        const x = padL + i * (chartW / days.length) + 2;
        const bh = Math.max(2, Math.round((d.mean_min / maxV) * chartH));
        const y = padTop + chartH - bh;
        bars += `<rect x="${x}" y="${y}" width="${bw}" height="${bh}" rx="3" fill="#2563eb" opacity="0.78"><title>${d.day}: ${d.mean_min} min</title></rect>` +
          `<text x="${x + bw / 2}" y="${H - 8}" text-anchor="middle" font-size="8" fill="var(--muted)">${d.day.slice(5)}</text>`;
      });
      div.innerHTML = `<svg viewBox="0 0 ${W} ${H}" width="100%" style="overflow:visible;display:block;">${bars}</svg>`;
    }

    async function createTatTarget(btn) {
      const exam_code = ($('tatTgtCode')?.value || '').trim().toUpperCase();
      const label = ($('tatTgtLabel')?.value || '').trim();
      const target_minutes = Number($('tatTgtMinutes')?.value);
      if (!exam_code || !label || !(target_minutes > 0)) { showToast('Champs incomplets', 'error'); return; }
      setLoading(btn, true);
      try {
        await api('/api/v1/tat/targets', { method: 'POST', headers: headers(), body: JSON.stringify({ exam_code, label, target_minutes }) });
        showToast('Cible TAT enregistrée', 'success');
        ['tatTgtCode', 'tatTgtLabel', 'tatTgtMinutes'].forEach(id => { if ($(id)) $(id).value = ''; });
        loadTat();
      } catch (e) { showToast(e.message === 'Conflict' ? 'Cible déjà définie' : 'Erreur (officier requis ?)', 'error'); }
      finally { setLoading(btn, false); }
    }

    async function deleteTatTarget(id, btn) {
      setLoading(btn, true);
      try { await api(`/api/v1/tat/targets/${id}`, { method: 'DELETE', headers: headers() }); showToast('Cible supprimée', 'success'); loadTat(); }
      catch (e) { showToast('Erreur suppression', 'error'); }
      finally { setLoading(btn, false); }
    }

    async function seedTatDefaults(btn) {
      setLoading(btn, true);
      try {
        const res = await api('/api/v1/tat/targets/seed-defaults', { method: 'POST', headers: headers() });
        showToast(`${res.created} cible(s) standard ajoutée(s)`, 'success');
        loadTat();
      } catch (e) { showToast('Erreur (officier requis ?)', 'error'); }
      finally { setLoading(btn, false); }
    }

    // ══════════════════════════════════════════════════════════════════════
    //  Module qualité — NC / CAPA
    // ══════════════════════════════════════════════════════════════════════
    const _ncSeverityBadge = (s) => ({
      minor: '<span class="pill">Mineure</span>',
      major: '<span class="pill" style="background:var(--amber);color:#fff;">Majeure</span>',
      critical: '<span class="pill bad">Critique</span>',
    }[s] || s);
    const _ncStatusLabel = { open: 'Ouverte', analysis: 'Analyse', action: 'Action', verification: 'Vérification', closed: 'Clôturée' };
    const _ncNextStatuses = {
      open: ['analysis', 'closed'], analysis: ['action', 'open', 'closed'],
      action: ['verification', 'analysis', 'closed'], verification: ['closed', 'action'], closed: [],
    };

    async function loadQuality() {
      try {
        const days = $('qualityCockpitDays')?.value || '30';
        const [dash, list, critical, tat, qc] = await Promise.all([
          api('/api/v1/quality/dashboard', { headers: headers(false) }),
          api(`/api/v1/quality/non-conformities${$('ncFilterStatus')?.value ? '?status=' + $('ncFilterStatus').value : ''}`, { headers: headers(false) }),
          api(`/api/v1/reports/critical-compliance?days=${encodeURIComponent(days)}&target_minutes=30`, { headers: headers(false) }).catch(() => null),
          api(`/api/v1/tat/dashboard?days=${encodeURIComponent(days)}`, { headers: headers(false) }).catch(() => null),
          api('/api/v1/reports/qc-summary', { headers: headers(false) }).catch(() => null),
        ]);
        $('qmTotal').textContent = dash.total;
        $('qmOpen').textContent = dash.open_count;
        $('qmOverdue').textContent = dash.overdue_count;
        $('qmCritical').textContent = dash.by_severity.critical || 0;
        _renderQualityCockpit({ dash, critical, tat, qc, days });
        const op = $('qmOverduePanel');
        if (op) { op.classList.remove('metric-rose', 'metric-teal'); op.classList.add(dash.overdue_count > 0 ? 'metric-rose' : 'metric-teal'); }
        setRows('ncTable', list.map(nc => {
          const due = nc.due_date ? new Date(nc.due_date).toLocaleDateString('fr-FR') : '—';
          const tr = row(
            `<td>${nc.id}</td>` +
            `<td>${security.escapeHtml(nc.title)}</td>` +
            `<td>${_ncSeverityBadge(nc.severity)}</td>` +
            `<td><span class="pill">${_ncStatusLabel[nc.status] || nc.status}</span></td>` +
            `<td>${due}</td>` +
            `<td><button class="ghost" onclick="openNcDetail(${nc.id})">Ouvrir</button></td>`
          );
          if (nc.severity === 'critical' && nc.status !== 'closed') tr.classList.add('row-critical');
          return tr;
        }));
      } catch (e) { showToast('Erreur chargement qualité', 'error'); log('loadQuality: ' + (e.message || e)); }
    }

    function _renderQualityCockpit({ dash, critical, tat, qc, days }) {
      const criticalLate = critical?.critical_late ?? 0;
      const criticalPending = critical?.critical_pending ?? 0;
      const tatLate = tat?.late_count ?? 0;
      const qcReject = qc?.reject_count ?? 0;
      const ncOpen = dash?.open_count ?? 0;
      if ($('qualityCriticalLate')) $('qualityCriticalLate').textContent = criticalLate;
      if ($('qualityTatLate')) $('qualityTatLate').textContent = tatLate;
      if ($('qualityQcReject')) $('qualityQcReject').textContent = qcReject;
      if ($('qualityNcRisk')) $('qualityNcRisk').textContent = ncOpen;
      const qcPanel = $('qualityQcPanel');
      if (qcPanel) { qcPanel.classList.remove('metric-rose', 'metric-teal', 'metric-amber'); qcPanel.classList.add(qcReject > 0 ? 'metric-rose' : (qc?.warn_count || 0) > 0 ? 'metric-amber' : 'metric-teal'); }
      const ncPanel = $('qualityNcRiskPanel');
      if (ncPanel) { ncPanel.classList.remove('metric-rose', 'metric-teal', 'metric-amber'); ncPanel.classList.add((dash?.overdue_count || 0) > 0 ? 'metric-rose' : ncOpen > 0 ? 'metric-amber' : 'metric-teal'); }
      if ($('qualityCockpitSummary')) {
        $('qualityCockpitSummary').textContent = `${criticalLate} critique(s) hors délai, ${tatLate} TAT en retard, ${qcReject} rejet(s) QC et ${ncOpen} NC ouverte(s) sur ${days} jour(s).`;
      }
      const rows = [
        { domain: 'Valeurs critiques', signal: `${criticalLate} hors délai · ${criticalPending} en attente`, action: 'Ouvrir rapport', view: 'reports', severe: criticalLate > 0 },
        { domain: 'TAT', signal: `${tatLate} examen(s) en retard`, action: 'Suivre TAT', view: 'tat', severe: tatLate > 0 },
        { domain: 'QC analytique', signal: `${qcReject} rejet(s) · ${qc?.warn_count || 0} alerte(s)`, action: 'Ouvrir QC', view: 'qc', severe: qcReject > 0 },
        { domain: 'NC/CAPA', signal: `${ncOpen} ouverte(s) · ${dash?.overdue_count || 0} en retard`, action: 'Voir NC', view: 'quality', severe: (dash?.overdue_count || 0) > 0 },
      ].map((item) => {
        const tr = row(
          `<td><strong>${security.escapeHtml(item.domain)}</strong></td>` +
          `<td>${security.escapeHtml(item.signal)}</td>` +
          `<td><button class="ghost" onclick="showView('${item.view}')">${security.escapeHtml(item.action)}</button></td>`
        );
        if (item.severe) tr.classList.add('row-warning');
        return tr;
      });
      setRows('qualityRiskTable', rows);
    }

    async function createNonConformity(btn) {
      const title = ($('ncTitle')?.value || '').trim();
      if (title.length < 3) { showToast('Titre trop court', 'error'); return; }
      setLoading(btn, true);
      try {
        const body = {
          title, description: $('ncDesc').value || null,
          source: $('ncSource').value, severity: $('ncSeverity').value,
        };
        if ($('ncDue').value) body.due_date = $('ncDue').value + 'T00:00:00';
        await api('/api/v1/quality/non-conformities', { method: 'POST', headers: headers(), body: JSON.stringify(body) });
        showToast('Non-conformité déclarée', 'success');
        ['ncTitle', 'ncDesc', 'ncDue'].forEach(id => { if ($(id)) $(id).value = ''; });
        loadQuality();
      } catch (e) { showToast('Erreur déclaration NC', 'error'); }
      finally { setLoading(btn, false); }
    }

    async function openNcDetail(ncId) {
      try {
        const nc = await api(`/api/v1/quality/non-conformities/${ncId}`, { headers: headers(false) });
        const transitions = (_ncNextStatuses[nc.status] || []).map(s =>
          `<button class="ghost" style="font-size:12px;" onclick="transitionNc(${nc.id},'${s}')">→ ${_ncStatusLabel[s]}</button>`
        ).join(' ');
        const actions = (nc.actions || []).map(a =>
          `<li>[${a.action_type === 'preventive' ? 'préventive' : 'corrective'}] ${security.escapeHtml(a.description)} — <strong>${a.status}</strong>` +
          (a.status !== 'done' ? ` <button class="ghost" style="font-size:11px;" onclick="completeAction(${a.id})">✓ Terminer</button>` : ' ✓') + `</li>`
        ).join('') || '<li style="color:var(--muted);">Aucune action.</li>';
        $('ncDetail').style.display = '';
        $('ncDetail').innerHTML =
          `<div style="display:flex;justify-content:space-between;align-items:center;">` +
            `<h3 style="margin:0;">NC #${nc.id} — ${security.escapeHtml(nc.title)}</h3>` +
            `<button class="ghost" onclick="$('ncDetail').style.display='none'">✕</button></div>` +
          `<p>${_ncSeverityBadge(nc.severity)} · Statut : <strong>${_ncStatusLabel[nc.status]}</strong> · Source : ${nc.source}</p>` +
          (nc.description ? `<p>${security.escapeHtml(nc.description)}</p>` : '') +
          (nc.root_cause ? `<p><strong>Cause racine :</strong> ${security.escapeHtml(nc.root_cause)}</p>` : '') +
          `<div style="margin:8px 0;"><strong>Transitions :</strong> ${transitions || '<em>terminal</em>'}</div>` +
          `<div style="margin:8px 0;"><strong>Actions correctives/préventives :</strong><ul>${actions}</ul></div>` +
          `<div class="form" style="max-width:480px;"><div><label>Nouvelle action</label><input id="ncActionDesc" placeholder="Description de l'action" /></div>` +
          `<div class="grid2"><div><label>Type</label><select id="ncActionType"><option value="corrective">Corrective</option><option value="preventive">Préventive</option></select></div>` +
          `<div style="display:flex;align-items:flex-end;"><button onclick="addNcAction(${nc.id},this)">Ajouter action</button></div></div></div>`;
        $('ncDetail').scrollIntoView({ behavior: 'smooth', block: 'nearest' });
      } catch (e) { showToast('Erreur chargement NC', 'error'); }
    }

    async function transitionNc(ncId, target) {
      let root_cause = null;
      if (target === 'analysis' || target === 'closed') {
        root_cause = prompt('Cause racine / commentaire (optionnel) :') || null;
      }
      try {
        await api(`/api/v1/quality/non-conformities/${ncId}/transition`, {
          method: 'POST', headers: headers(), body: JSON.stringify({ status: target, root_cause }),
        });
        showToast('Statut mis à jour', 'success');
        await openNcDetail(ncId); loadQuality();
      } catch (e) { showToast(e.message || 'Transition refusée', 'error'); }
    }

    async function addNcAction(ncId, btn) {
      const desc = ($('ncActionDesc')?.value || '').trim();
      if (desc.length < 3) { showToast('Description trop courte', 'error'); return; }
      setLoading(btn, true);
      try {
        await api(`/api/v1/quality/non-conformities/${ncId}/actions`, {
          method: 'POST', headers: headers(),
          body: JSON.stringify({ description: desc, action_type: $('ncActionType').value }),
        });
        showToast('Action ajoutée', 'success');
        await openNcDetail(ncId);
      } catch (e) { showToast('Erreur ajout action', 'error'); }
      finally { setLoading(btn, false); }
    }

    async function completeAction(actionId) {
      try {
        await api(`/api/v1/quality/actions/${actionId}`, {
          method: 'PATCH', headers: headers(),
          body: JSON.stringify({ status: 'done', effectiveness_checked: true }),
        });
        showToast('Action terminée', 'success');
        loadQuality();
        const open = $('ncDetail'); if (open && open.style.display !== 'none') {
          const m = open.innerHTML.match(/NC #(\d+)/); if (m) openNcDetail(Number(m[1]));
        }
      } catch (e) { showToast('Erreur', 'error'); }
    }

    function _renderTatChart(tatData) {
      const div = $('tatChartDiv');
      if (!div) return;
      if (!tatData.length) {
        div.innerHTML = '<p style="color:var(--muted);text-align:center;padding:24px 0;">Aucune donnée TAT sur la période</p>';
        return;
      }
      const maxTat = Math.max(...tatData.map(d => d.mean_h), 1);
      const barH = 26;
      const gap = 7;
      const labelW = 130;
      const totalW = 480;
      const barAreaW = totalW - labelW - 40;
      const svgH = tatData.length * (barH + gap) + 16;
      let bars = '';
      tatData.forEach((d, i) => {
        const y = i * (barH + gap) + 8;
        const bw = Math.max(2, Math.round((d.mean_h / maxTat) * barAreaW));
        const color = d.mean_h > 48 ? '#be123c' : d.mean_h > 24 ? '#b45309' : '#0f766e';
        bars +=
          `<text x="${labelW - 8}" y="${y + barH / 2 + 4}" text-anchor="end" font-size="11" fill="currentColor"` +
          ` style="font-family:var(--font);">${security.escapeHtml(d.equipment)}</text>` +
          `<rect x="${labelW}" y="${y}" width="${bw}" height="${barH}" rx="4" fill="${color}" opacity="0.82"/>` +
          `<text x="${labelW + bw + 6}" y="${y + barH / 2 + 4}" font-size="11" fill="currentColor"` +
          ` style="font-family:var(--font);">${d.mean_h}h <tspan fill="var(--muted)" font-size="10">(n=${d.count})</tspan></text>`;
      });
      div.innerHTML = `<svg viewBox="0 0 ${totalW} ${svgH}" width="100%" style="overflow:visible;display:block;">${bars}</svg>`;
    }

    function _renderWeeklyChart(weeks) {
      const div = $('weeklyChartDiv');
      if (!div) return;
      if (!weeks.length) {
        div.innerHTML = '<p style="color:var(--muted);text-align:center;padding:24px 0;">Aucune donnée hebdomadaire</p>';
        return;
      }
      const maxV = Math.max(...weeks.map(w => w.count), 1);
      const W = 460; const H = 150;
      const padL = 4; const padR = 4; const padTop = 16; const padBot = 24;
      const chartW = W - padL - padR;
      const chartH = H - padTop - padBot;
      const bw = Math.floor(chartW / weeks.length) - 4;
      let bars = '';
      weeks.forEach((w, i) => {
        const x = padL + i * (chartW / weeks.length) + 2;
        const bh = Math.max(2, Math.round((w.count / maxV) * chartH));
        const y = padTop + chartH - bh;
        const color = '#2563eb';
        bars +=
          `<rect x="${x}" y="${y}" width="${bw}" height="${bh}" rx="3" fill="${color}" opacity="0.76"/>` +
          `<text x="${x + bw / 2}" y="${H - 6}" text-anchor="middle" font-size="9" fill="var(--muted)"` +
          ` style="font-family:var(--font);">${security.escapeHtml(w.label)}</text>` +
          (w.count > 0 ? `<text x="${x + bw / 2}" y="${y - 3}" text-anchor="middle" font-size="9" fill="currentColor">${w.count}</text>` : '');
      });
      div.innerHTML = `<svg viewBox="0 0 ${W} ${H}" width="100%" style="overflow:visible;display:block;">${bars}</svg>`;
    }

    // ── Password toggle ────────────────────────────────────────────────────────
    function togglePw() {
      const inp = $('password');
      const btn = $('pwToggleBtn');
      if (!inp) return;
      const isText = inp.type === 'text';
      inp.type = isText ? 'password' : 'text';
      if (btn) btn.textContent = isText ? '👁' : '🙈';
    }

    // ── Topbar live clock ─────────────────────────────────────────────────────
    let _clockInterval = null;
    function startClock() {
      const el = $('topbarClock');
      if (!el) return;
      function tick() {
        el.textContent = new Date().toLocaleTimeString('fr-FR', {
          hour: '2-digit', minute: '2-digit', second: '2-digit'
        });
      }
      tick();
      if (_clockInterval) clearInterval(_clockInterval);
      _clockInterval = setInterval(tick, 1000);
    }

    // ── Log panel collapsible ─────────────────────────────────────────────────
    function toggleLog() {
      $('logPanel')?.classList.toggle('log-collapsed');
    }

    // Initialiser le moteur IA au chargement de la page
    document.addEventListener('DOMContentLoaded', () => {
      closeSidebar();
      // Initialiser l'IA après un court délai pour éviter de bloquer le chargement
      setTimeout(() => {
        ruggyAI.init().catch(error => {
          console.error('Échec initialisation IA:', error);
          showToast('Initialisation IA échouée - Certaines fonctionnalités limitées', 'warning');
        });
      }, 2000);
    });

    window.addEventListener('resize', () => {
      if (window.innerWidth > 980) closeSidebar();
    });
