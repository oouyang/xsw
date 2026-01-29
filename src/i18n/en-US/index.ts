// English (US) translations
export default {
  // Common
  common: {
    home: 'Home',
    settings: 'Settings',
    chapters: 'Chapters',
    close: 'Close',
    done: 'Done',
    cancel: 'Cancel',
    retry: 'Retry',
    loading: 'Loading...',
    error: 'Error',
    success: 'Success',
  },

  // Navigation
  nav: {
    home: 'Read Novels',
    chapters: 'Chapters',
    chapterList: 'Chapter List',
    prevChapter: 'Previous Chapter',
    nextChapter: 'Next Chapter',
    backToChapterList: 'Back to Chapter List',
    goBack: 'Go Back',
  },

  // Settings
  settings: {
    title: 'Reading Settings',
    darkMode: 'Dark Mode',
    lightMode: 'Light',
    darkModeLabel: 'Dark',
    fontSize: 'Font Size',
    preview: 'Preview',
    previewText: 'This is a preview of the reading interface. You can adjust the font size and dark mode to get the best reading experience.',
  },

  // Font sizes
  fontSizes: {
    largest: 'Largest',
    larger: 'Larger',
    large: 'Large',
    mediumLarge: 'Medium Large',
    medium: 'Medium',
    small: 'Small',
    smallest: 'Smallest',
  },

  // Book
  book: {
    author: 'Author',
    type: 'Type',
    status: 'Status',
    updated: 'Updated',
    lastChapter: 'Latest Chapter',
    latestPrefix: '⚡ Latest',
    intro: 'Introduction',
    loadInfoFailed: 'Failed to load book info',
  },

  // Chapter
  chapter: {
    chapter: 'Chapter',
    prev: 'Prev',
    next: 'Next',
    bypassCache: 'Bypass cache',
    loadFailed: 'Failed to load chapter',
    loadContentFailed: 'Failed to load content',
    loadTimeout: 'Load timeout, please retry. The server may be processing requests or network connection is slow.',
    notFound: 'Chapter not found',
    readingProgress: 'Reading Progress',
    displayChapters: 'Showing chapters {start}～{end} (Total: {total})',
    noChaptersOnPage: 'No chapters on this page',
    loadingChapters: 'Loading chapters...',
    loadChaptersFailed: 'Failed to load chapter list',
    reloadChapters: 'Reload',
    loadingFirstPages: 'Loading first {pages} pages...',
    loadingRemainingInBackground: 'Loading remaining chapters in background...',
    phase2LoadingWarning: 'Background loading incomplete (first 3 pages available)',
    phase2LoadingComplete: 'All chapters loaded',
    loadingProgress: 'Loaded {loaded} / {total} chapters',
    estimatedReadingTime: 'Estimated Reading Time',
    readingTimeMinutes: '{minutes} min',
    readingTimeHoursMinutes: '{hours} hr {minutes} min',
  },

  // Categories
  category: {
    categories: 'Categories',
    books: 'Books',
    viewAll: 'View All',
  },

  // Errors
  error: {
    loadFailed: 'Load failed',
    networkError: 'Network error',
    notFound: '404: Not found',
    serverError: 'Server error',
  },

  // Actions
  action: {
    scrollTop: 'Scroll to top',
    scrollBottom: 'Scroll to bottom',
    goBack: 'Go back',
    showHeader: 'Show Header',
  },

  // Search
  search: {
    title: 'Search Results',
    placeholder: 'Search books, authors or content...',
    keyword: 'Search Keyword',
    searching: 'Searching...',
    noResults: 'No results found',
    resultsCount: 'Found {count} results from {books} books',
    searchFailed: 'Search failed, please try again later',
    tabs: {
      all: 'All',
      books: 'Books',
      chapters: 'Chapters',
      content: 'Content',
    },
    matchTypes: {
      book_name: 'Book Name',
      author: 'Author',
      chapter_title: 'Chapter Title',
      chapter_content: 'Chapter Content',
    },
  },

  // Language
  language: {
    zhTW: '繁體中文',
    zhCN: '简体中文',
    enUS: 'English',
  },

  // Admin
  admin: {
    title: 'Admin Panel',
    login: 'Admin Login',
    logout: 'Logout',
    username: 'Username',
    password: 'Password',
    email: 'Email',
    loginButton: 'Login',
    loginSuccess: 'Admin logged in successfully',
    loginFailed: 'Invalid credentials',
    logoutSuccess: 'Admin logged out',

    // Google Sign-In
    googleSignIn: 'Sign in with Google',
    googleSignInFailed: 'Google Sign-In failed',
    passwordLogin: 'Password Login (Fallback)',
    passwordLoginCaption: 'For emergency access only',

    // Change Password
    changePassword: 'Change Password',
    currentPassword: 'Current Password',
    newPassword: 'New Password',
    confirmPassword: 'Confirm New Password',
    passwordChanged: 'Password changed successfully',
    passwordChangeFailed: 'Failed to change password',

    // Validation
    allFieldsRequired: 'All fields are required',
    passwordMismatch: 'New passwords do not match',
    passwordTooShort: 'Password must be at least 4 characters',
    incorrectPassword: 'Current password is incorrect',

    // Tabs
    tabs: {
      stats: 'Stats',
      jobs: 'Jobs',
      cache: 'Cache',
      books: 'Books',
      smtp: 'SMTP',
    },

    // Stats
    stats: {
      cache: 'Cache Stats',
      jobs: 'Job Stats',
      midnightSync: 'Midnight Sync',
      periodicSync: 'Periodic Sync (6h)',
      books: 'Books',
      chapters: 'Chapters',
      memory: 'Memory',
      pending: 'Pending',
      completed: 'Completed',
      failed: 'Failed',
      syncing: 'Syncing',
      total: 'Total',
      nextSync: 'Next',
      lastSync: 'Last',
      interval: 'Interval',
      priority: 'Priority',
      active: 'Active',
    },

    // Actions
    actions: {
      midnightSync: 'Midnight Sync Actions',
      enqueue: 'Enqueue',
      trigger: 'Trigger',
      clear: 'Clear',
      refresh: 'Refresh',
      clearCache: 'Clear Memory Cache',
      clearHistory: 'Clear Job History',
      forceResync: 'Force Resync Book',
      initSync: 'Initialize Full Sync',
      saveSMTP: 'Save Settings',
      testSMTP: 'Test Connection',
    },

    // Tooltips
    tooltips: {
      enqueue: 'Enqueue unfinished books',
      trigger: 'Trigger sync now',
      clear: 'Clear completed/failed',
      refresh: 'Refresh stats',
      clearCache: 'Clear in-memory cache (DB intact)',
      clearHistory: 'Clear completed and failed job history',
      forceResync: 'Force resync to fix missing chapters',
      changePassword: 'Change Password',
      initSync: 'WARNING: Deletes all data and rescans from scratch',
    },

    // Book Management
    bookManagement: {
      title: 'Book Management',
      bookId: 'Book ID',
      bookIdPlaceholder: 'Enter book ID to resync',
      bookIdHint: 'Book ID to force resync (e.g., 1677042)',
    },

    // Init Sync
    initSync: {
      title: 'Initialize Full Sync',
      categories: 'Categories',
      categoriesHint: 'Number of categories to scan (1-20)',
      pagesPerCategory: 'Pages/Category',
      pagesHint: 'Pages per category (1-50)',
    },

    // Confirmations
    confirm: {
      title: 'Confirm',
      clearCache: 'Clear in-memory cache? This will not affect the database.',
      clearHistory: 'Clear job history? This will remove all completed and failed job records.',
      forceResync: 'Force resync book {bookId}? This will clear cache and re-fetch all chapters.',
      initSync: '<strong>WARNING: Destructive Operation!</strong><br/><br/>This will:<br/>• Delete ALL books, chapters, and cached data<br/>• Scan categories from homepage<br/>• Queue all discovered books for sync<br/><br/>Are you sure you want to continue?',
    },

    // Messages
    messages: {
      statsRefreshed: 'Stats refreshed',
      enqueuedBooks: 'Enqueued {count} books',
      syncTriggered: 'Midnight sync triggered',
      clearedEntries: 'Cleared {count} entries',
      cacheCleared: 'Memory cache cleared',
      historyCleared: 'Cleared {count} job records',
      bookQueued: 'Book queued for resync',
      bookAlreadySyncing: 'Book is currently being synced',
      enterBookId: 'Please enter a book ID',

      initSyncSuccess: 'Initialized sync: queued {queued} books from {categories} categories',
      initSyncFailed: 'Failed to initialize sync',

      // Errors
      fetchStatsFailed: 'Failed to fetch stats',
      enqueueFailed: 'Failed to enqueue books',
      triggerFailed: 'Failed to trigger sync',
      clearFailed: 'Failed to clear completed',
      cacheClearFailed: 'Failed to clear cache',
      historyClearFailed: 'Failed to clear job history',
      resyncFailed: 'Failed to resync book',
    },

    // SMTP
    smtp: {
      title: 'SMTP Configuration',
      host: 'SMTP Host',
      hostHint: 'e.g., smtp.gmail.com',
      port: 'Port',
      portHint: '587 for TLS, 465 for SSL, 25 for plain',
      user: 'Username',
      userHint: 'SMTP username or email',
      password: 'Password',
      passwordHint: 'SMTP password or app password',
      useTLS: 'Use TLS',
      useSSL: 'Use SSL',
      fromEmail: 'From Email',
      fromEmailHint: 'Leave empty to use SMTP username',
      fromName: 'From Name',
      lastTest: 'Last Test',
      testSuccess: 'Connection successful',
      testFailed: 'Connection failed',
      saveSuccess: 'SMTP settings saved successfully',
      saveFailed: 'Failed to save SMTP settings',
    },
  },
};
