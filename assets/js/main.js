/* Ruvex Software Supply — demo catalog behaviour.
   No network, no accounts. Saved tools live in this browser only. */
(function () {
  'use strict';

  var TOOLS = {
    pull: {
      plate: '009',
      name: 'Pull',
      job: 'yt-dlp downloader',
      category: 'media',
      categoryLabel: 'Media',
      icon: 'pull',
      readme: 'Paste a link, pick video or audio, choose a folder. Pull is a plain front-end for yt-dlp: quality, format and extras in one work order, with live progress while it runs.',
      bullets: [
        'Video or audio, with quality and format choices',
        'Runs on your PC, no account, no upload'
      ]
    }
  };

  var SAVED_KEY = 'ruvex.saved.v1';
  var VIEW_KEY = 'ruvex.view.v1';
  var TOTAL = Object.keys(TOOLS).length;

  var shelf = document.getElementById('shelf');
  var shelfGrid = document.getElementById('shelf-grid');
  var shelfHint = document.getElementById('shelf-hint');
  var toolList = document.getElementById('tool-list');
  var emptyState = document.getElementById('empty-state');
  var filters = document.querySelector('.filters');
  var filterCount = document.getElementById('filter-count');
  var viewButtons = document.querySelectorAll('.view-btn');
  var counter = document.getElementById('counter');
  var counterPlate = document.getElementById('counter-plate');
  var counterTitle = document.getElementById('counter-title');
  var counterJob = document.getElementById('counter-job');
  var counterReadme = document.getElementById('counter-readme');
  var counterBullets = document.getElementById('counter-bullets');
  var counterIconUse = document.getElementById('counter-icon-use');
  var counterAnnouncer = document.getElementById('counter-announcer');
  var saveBtn = document.getElementById('save-btn');
  var saveLabel = document.getElementById('save-label');
  var receiptSaved = document.getElementById('receipt-saved');
  var receipt = document.querySelector('.receipt');
  var toast = document.getElementById('toast');
  var reducedMotion = window.matchMedia('(prefers-reduced-motion: reduce)');
  var narrowScreen = window.matchMedia('(max-width: 980px)');

  var currentTool = 'pull';
  var activeFilter = 'all';
  var currentView = 'shelf';
  var toastTimer = null;

  function readStorage(key) {
    try {
      return window.localStorage.getItem(key);
    } catch (err) {
      return null;
    }
  }

  function writeStorage(key, value) {
    try {
      window.localStorage.setItem(key, value);
    } catch (err) {
      /* Storage can be unavailable; the page still works for this visit. */
    }
  }

  function loadSaved() {
    var stored = readStorage(SAVED_KEY);
    var ids = [];

    if (stored) {
      try {
        var parsed = JSON.parse(stored);
        if (Array.isArray(parsed)) {
          ids = parsed.filter(function (id) {
            return Object.prototype.hasOwnProperty.call(TOOLS, id);
          });
        }
      } catch (err) {
        ids = [];
      }
    }

    return new Set(ids);
  }

  var saved = loadSaved();

  function getVisibleShelfTools() {
    return Array.prototype.slice.call(shelfGrid.querySelectorAll('.tool')).filter(function (article) {
      return !article.hidden;
    });
  }

  function getVisibleListItems() {
    return Array.prototype.slice.call(toolList.querySelectorAll('.list-item')).filter(function (item) {
      return !item.hidden;
    });
  }

  function syncSelectionState() {
    shelfGrid.querySelectorAll('.tool').forEach(function (article) {
      var isCurrent = article.dataset.tool === currentTool;
      article.classList.toggle('is-selected', isCurrent);
      var button = article.querySelector('.tool-btn');
      if (button) {
        button.setAttribute('aria-pressed', String(isCurrent));
      }
    });

    toolList.querySelectorAll('.list-item').forEach(function (item) {
      var isCurrent = item.dataset.tool === currentTool;
      var button = item.querySelector('.list-btn');
      item.classList.toggle('is-selected', isCurrent);
      if (button) {
        button.classList.toggle('is-selected', isCurrent);
        button.setAttribute('aria-pressed', String(isCurrent));
      }
    });
  }

  function syncSaveState() {
    document.querySelectorAll('.tool').forEach(function (article) {
      article.classList.toggle('is-saved', saved.has(article.dataset.tool));
    });
    document.querySelectorAll('.list-item').forEach(function (item) {
      item.classList.toggle('is-saved', saved.has(item.dataset.tool));
    });

    var isSaved = saved.has(currentTool);
    saveBtn.setAttribute('aria-pressed', String(isSaved));
    saveLabel.textContent = isSaved ? 'Saved for later' : 'Save for later';
    saveBtn.setAttribute(
      'aria-label',
      isSaved
        ? 'Remove ' + TOOLS[currentTool].name + ' from saved tools'
        : 'Save ' + TOOLS[currentTool].name + ' for later'
    );

    receiptSaved.textContent = String(saved.size);
  }

  function updateCounter(toolId, animate) {
    var tool = TOOLS[toolId];
    if (!tool) {
      return;
    }

    counterPlate.textContent = 'NO. ' + tool.plate;
    counterTitle.textContent = tool.name;
    counterJob.textContent = tool.job.toUpperCase();
    counterReadme.textContent = tool.readme;
    counterIconUse.setAttribute('href', '#icon-' + tool.icon);

    counterBullets.replaceChildren();
    tool.bullets.forEach(function (text) {
      var item = document.createElement('li');
      item.textContent = text;
      counterBullets.appendChild(item);
    });

    if (animate) {
      counter.classList.remove('is-swapping');
      void counter.offsetWidth;
      counter.classList.add('is-swapping');
    }
  }

  function announceSelection() {
    var tool = TOOLS[currentTool];
    counterAnnouncer.textContent = tool.name + ', ' + tool.job.toLowerCase() + ', is on the counter.';
  }

  function scrollToCounter() {
    if (!narrowScreen.matches) {
      return;
    }
    counter.scrollIntoView({
      behavior: reducedMotion.matches ? 'auto' : 'smooth',
      block: 'start'
    });
  }

  function selectTool(toolId, options) {
    if (!TOOLS[toolId]) {
      return;
    }

    var opts = options || {};
    var changed = currentTool !== toolId;
    currentTool = toolId;
    syncSelectionState();
    updateCounter(toolId, Boolean(opts.animate) && changed);
    syncSaveState();

    if (opts.announce) {
      announceSelection();
    }
    if (opts.scroll) {
      scrollToCounter();
    }
  }

  function showToast(message) {
    window.clearTimeout(toastTimer);
    toast.textContent = message;
    toast.classList.add('is-visible');
    toastTimer = window.setTimeout(function () {
      toast.classList.remove('is-visible');
    }, 2800);
  }

  function persistSaved() {
    writeStorage(SAVED_KEY, JSON.stringify(Array.from(saved)));
  }

  function toggleSaved() {
    var tool = TOOLS[currentTool];

    if (saved.has(currentTool)) {
      saved.delete(currentTool);
      showToast(tool.name + ' removed from saved.');
    } else {
      saved.add(currentTool);
      showToast(tool.name + ' saved for later in this browser.');
    }

    persistSaved();
    syncSaveState();

    if (receipt) {
      receipt.classList.remove('is-bumped');
      void receipt.offsetWidth;
      receipt.classList.add('is-bumped');
    }
  }

  function applyFilter(filter) {
    var valid = filter === 'all' || Array.prototype.some.call(
      shelfGrid.querySelectorAll('.tool'),
      function (article) { return article.dataset.category === filter; }
    );
    var nextFilter = valid ? filter : 'all';
    var count = 0;

    activeFilter = nextFilter;

    filters.querySelectorAll('.filter').forEach(function (button) {
      var isActive = button.dataset.filter === nextFilter;
      button.classList.toggle('is-active', isActive);
      button.setAttribute('aria-pressed', String(isActive));
    });

    shelfGrid.querySelectorAll('.tool').forEach(function (article) {
      var match = nextFilter === 'all' || article.dataset.category === nextFilter;
      article.hidden = !match;
      if (match) {
        count += 1;
      }
    });

    toolList.querySelectorAll('.list-item').forEach(function (item) {
      var match = nextFilter === 'all' || item.dataset.category === nextFilter;
      item.hidden = !match;
    });

    filterCount.textContent = 'Showing ' + count + ' of ' + TOTAL;
    emptyState.hidden = count !== 0;
  }

  function setView(view, persist) {
    var nextView = view === 'list' ? 'list' : 'shelf';
    currentView = nextView;

    shelfGrid.hidden = nextView !== 'shelf';
    shelfHint.hidden = nextView !== 'shelf';
    toolList.hidden = nextView !== 'list';

    viewButtons.forEach(function (button) {
      var isActive = button.dataset.view === nextView;
      button.classList.toggle('is-active', isActive);
      button.setAttribute('aria-pressed', String(isActive));
    });

    if (persist !== false) {
      writeStorage(VIEW_KEY, nextView);
    }
  }

  function gridColumnCount() {
    var columns = window.getComputedStyle(shelfGrid).gridTemplateColumns;
    var count = columns.split(' ').filter(Boolean).length;
    return count > 0 ? count : 1;
  }

  function handleKeyboardNavigation(event, mode) {
    if (event.altKey || event.ctrlKey || event.metaKey || event.shiftKey) {
      return;
    }

    var button = event.target.closest('button[data-tool]');
    if (!button) {
      return;
    }

    var buttons;
    var columns;

    if (mode === 'shelf') {
      buttons = getVisibleShelfTools().map(function (article) {
        return article.querySelector('.tool-btn');
      });
      columns = gridColumnCount();
    } else {
      buttons = getVisibleListItems().map(function (item) {
        return item.querySelector('.list-btn');
      });
      columns = 1;
    }

    var index = buttons.indexOf(button);
    if (index === -1) {
      return;
    }

    var nextIndex = index;

    switch (event.key) {
      case 'ArrowLeft':
        nextIndex = index - 1;
        break;
      case 'ArrowRight':
        nextIndex = index + 1;
        break;
      case 'ArrowUp':
        nextIndex = index - columns;
        break;
      case 'ArrowDown':
        nextIndex = index + columns;
        break;
      case 'Home':
        nextIndex = 0;
        break;
      case 'End':
        nextIndex = buttons.length - 1;
        break;
      default:
        return;
    }

    if (nextIndex < 0 || nextIndex >= buttons.length || nextIndex === index) {
      return;
    }

    event.preventDefault();
    var nextButton = buttons[nextIndex];
    nextButton.focus();
    selectTool(nextButton.dataset.tool, { animate: true });
  }

  function initializeShelfLabels() {
    shelfGrid.querySelectorAll('.tool').forEach(function (article) {
      var tool = TOOLS[article.dataset.tool];
      var shelfPad = article.querySelector('.tool-shelf');
      if (tool && shelfPad) {
        shelfPad.dataset.label = tool.plate + ' · ' + tool.name.toUpperCase();
      }
    });
  }

  function initializeCounts() {
    filters.querySelectorAll('.filter').forEach(function (button) {
      var filter = button.dataset.filter;
      var count = filter === 'all'
        ? TOTAL
        : Array.prototype.filter.call(shelfGrid.querySelectorAll('.tool'), function (article) {
          return article.dataset.category === filter;
        }).length;
      var counterEl = button.querySelector('span');
      if (counterEl) {
        counterEl.textContent = String(count);
      }
    });
  }

  /* Events */

  shelfGrid.addEventListener('click', function (event) {
    var article = event.target.closest('.tool');
    if (!article) {
      return;
    }
    selectTool(article.dataset.tool, {
      animate: true,
      announce: true,
      scroll: event.detail > 0
    });
  });

  toolList.addEventListener('click', function (event) {
    var item = event.target.closest('.list-item');
    if (!item) {
      return;
    }
    selectTool(item.dataset.tool, {
      animate: true,
      announce: true,
      scroll: event.detail > 0
    });
  });

  shelfGrid.addEventListener('keydown', function (event) {
    handleKeyboardNavigation(event, 'shelf');
  });

  toolList.addEventListener('keydown', function (event) {
    handleKeyboardNavigation(event, 'list');
  });

  filters.addEventListener('click', function (event) {
    var button = event.target.closest('.filter');
    if (!button) {
      return;
    }
    applyFilter(button.dataset.filter);
  });

  viewButtons.forEach(function (button) {
    button.addEventListener('click', function () {
      setView(button.dataset.view);
    });
  });

  saveBtn.addEventListener('click', toggleSaved);

  counter.addEventListener('animationend', function (event) {
    if (event.animationName === 'counter-swap') {
      counter.classList.remove('is-swapping');
    }
  });

  receipt.addEventListener('animationend', function (event) {
    if (event.animationName === 'receipt-bump') {
      receipt.classList.remove('is-bumped');
    }
  });

  window.addEventListener('storage', function (event) {
    if (event.key === SAVED_KEY) {
      saved = loadSaved();
      syncSaveState();
    }
    if (event.key === VIEW_KEY) {
      setView(event.newValue === 'list' ? 'list' : 'shelf', false);
    }
  });

  /* Boot */

  document.documentElement.classList.add('js');
  initializeShelfLabels();
  initializeCounts();
  setView(readStorage(VIEW_KEY), false);
  applyFilter('all');
  selectTool('pull', { animate: false, announce: false });
})();
