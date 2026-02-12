// Traditional Chinese (Taiwan) translations
export default {
  // 常用
  common: {
    home: '首頁',
    settings: '設定',
    chapters: '章節',
    close: '關閉',
    done: '完成',
    cancel: '取消',
    retry: '重試',
    loading: '載入中...',
    error: '錯誤',
    success: '成功',
    remove: '移除',
    clear: '清除',
  },

  // 導航
  nav: {
    home: '看小說',
    chapters: '目錄',
    chapterList: '章節列表',
    prevChapter: '上一章',
    nextChapter: '下一章',
    backToChapterList: '返回章節列表',
    goBack: '返回',
  },

  // 設定
  settings: {
    title: '閱讀設定',
    darkMode: '深色模式',
    lightMode: '淺色',
    darkModeLabel: '深色',
    fontSize: '字體大小',
    preview: '預覽',
    previewText: '這是閱讀介面的預覽文字，您可以調整字體大小和深色模式來獲得最佳的閱讀體驗。',
  },

  // 字體大小
  fontSizes: {
    largest: '最大',
    larger: '超大',
    large: '大',
    mediumLarge: '較大',
    medium: '中等',
    small: '較小',
    smallest: '最小',
  },

  // 書籍
  book: {
    author: '作者',
    type: '分類',
    status: '狀態',
    updated: '更新',
    lastChapter: '最新章節',
    latestPrefix: '⚡ 最新',
    intro: '簡介',
    loadInfoFailed: '載入書籍資訊失敗',
  },

  // 章節
  chapter: {
    chapter: '章',
    prev: '上一章',
    next: '下一章',
    bypassCache: '略過快取',
    loadFailed: '載入章節失敗',
    loadContentFailed: '載入內容失敗',
    loadTimeout: '載入超時，請重試。伺服器可能正在處理請求或網路連線緩慢。',
    notFound: '找不到章節',
    readingProgress: '閱讀進度',
    displayChapters: '顯示第 {start}～{end} 章 (共 {total} 章)',
    noChaptersOnPage: '此頁暫無章節',
    loadingChapters: '載入章節中...',
    loadChaptersFailed: '載入章節列表失敗',
    reloadChapters: '重新載入',
    loadingFirstPages: '載入前 {pages} 頁章節...',
    loadingRemainingInBackground: '背景載入剩餘章節...',
    phase2LoadingWarning: '背景載入未完成（前3頁已可用）',
    phase2LoadingComplete: '所有章節已載入完成',
    loadingProgress: '已載入 {loaded} / {total} 章',
    estimatedReadingTime: '預計閱讀時間',
    readingTimeMinutes: '{minutes} 分鐘',
    readingTimeHoursMinutes: '{hours} 小時 {minutes} 分鐘',
    keyboardHint: '鍵盤快捷鍵：P (上一章) • N (下一章) • Enter (章節列表)',
  },

  // 分類
  category: {
    categories: '分類',
    books: '書籍',
    viewAll: '查看全部',
  },

  // 錯誤
  error: {
    loadFailed: '載入失敗',
    networkError: '網路錯誤',
    notFound: '404: 找不到',
    serverError: '伺服器錯誤',
  },

  // 動作
  action: {
    scrollTop: '回到頂部',
    scrollBottom: '到達底部',
    goBack: '返回',
    showHeader: '顯示標題列',
    share: '分享',
    copyLink: '複製連結',
    continueReading: '繼續閱讀',
  },

  // 首頁
  dashboard: {
    continueReading: '繼續閱讀',
  },

  // 使用者認證
  userAuth: {
    login: '登入',
    logout: '登出',
    loginTitle: '登入以儲存進度',
    loginSubtitle: '閱讀進度將在所有裝置間同步。',
    signInGoogle: '使用 Google 登入',
    signInFacebook: '使用 Facebook 登入',
    signInApple: '使用 Apple 登入',
    signInWeChat: '使用微信登入',
    syncMessage: '閱讀進度將在所有裝置間同步。',
    loggingIn: '登入中...',
  },

  // 搜尋
  search: {
    title: '搜尋結果',
    placeholder: '搜尋書名、作者或內容...',
    keyword: '搜尋關鍵字',
    searching: '搜尋中...',
    noResults: '未找到相關結果',
    resultsCount: '找到 {count} 筆結果，來自 {books} 本書籍',
    searchFailed: '搜尋失敗，請稍後再試',
    tabs: {
      all: '全部',
      books: '書籍',
      chapters: '章節',
      content: '內容',
    },
    matchTypes: {
      book_name: '書名',
      author: '作者',
      chapter_title: '章節標題',
      chapter_content: '章節內容',
    },
  },

  // 語言
  language: {
    zhTW: '繁體中文',
    zhCN: '简体中文',
    enUS: 'English',
  },

  // 管理員
  admin: {
    title: '管理面板',
    login: '管理員登入',
    logout: '登出',
    username: '使用者名稱',
    password: '密碼',
    email: '電子郵件',
    loginButton: '登入',
    loginSuccess: '登入成功',
    loginFailed: '使用者名稱或密碼錯誤',
    logoutSuccess: '已登出',

    // Google Sign-In
    googleSignIn: '使用 Google 登入',
    googleSignInFailed: 'Google 登入失敗',
    passwordLogin: '密碼登入（備用）',
    passwordLoginCaption: '僅供緊急存取使用',

    // 修改密碼
    changePassword: '修改密碼',
    currentPassword: '目前密碼',
    newPassword: '新密碼',
    confirmPassword: '確認新密碼',
    passwordChanged: '密碼修改成功',
    passwordChangeFailed: '密碼修改失敗',

    // 驗證
    allFieldsRequired: '所有欄位都是必填的',
    passwordMismatch: '兩次輸入的新密碼不一致',
    passwordTooShort: '密碼長度至少為4個字元',
    incorrectPassword: '目前密碼不正確',

    // 標籤頁
    tabs: {
      stats: '統計',
      jobs: '任務',
      cache: '快取',
      books: '書籍',
      smtp: 'SMTP',
    },

    // 統計
    stats: {
      cache: '快取統計',
      jobs: '任務統計',
      midnightSync: '午夜同步',
      periodicSync: '定期同步 (6小時)',
      books: '書籍',
      chapters: '章節',
      memory: '記憶體',
      pending: '待處理',
      completed: '已完成',
      failed: '失敗',
      syncing: '同步中',
      total: '總計',
      nextSync: '下次',
      lastSync: '上次',
      interval: '間隔',
      priority: '優先級',
      active: '活躍',
    },

    // 操作
    actions: {
      midnightSync: '午夜同步操作',
      enqueue: '加入佇列',
      trigger: '觸發',
      clear: '清理',
      refresh: '重新整理',
      clearCache: '清除記憶體快取',
      clearHistory: '清除任務歷史',
      forceResync: '強制重新同步',
      initSync: '初始化完整同步',
      saveSMTP: '儲存設定',
      testSMTP: '測試連接',
    },

    // 提示
    tooltips: {
      enqueue: '將未完成的書籍加入佇列',
      trigger: '立即觸發同步',
      clear: '清除已完成/失敗的記錄',
      refresh: '重新整理統計資料',
      clearCache: '清除記憶體快取（資料庫不受影響）',
      clearHistory: '清除已完成和失敗的任務記錄',
      forceResync: '強制重新同步以修復缺失的章節',
      changePassword: '修改密碼',
      initSync: '警告：刪除所有資料並從頭重新掃描',
    },

    // 書籍管理
    bookManagement: {
      title: '書籍管理',
      bookId: '書籍ID',
      bookIdPlaceholder: '輸入要重新同步的書籍ID',
      bookIdHint: '要強制重新同步的書籍ID（例如：1677042）',
    },

    // 初始化同步
    initSync: {
      title: '初始化完整同步',
      categories: '分類數量',
      categoriesHint: '要掃描的分類數量（1-20）',
      pagesPerCategory: '每類頁數',
      pagesHint: '每個分類的頁數（1-50）',
    },

    // 確認
    confirm: {
      title: '確認',
      clearCache: '清除記憶體快取？這不會影響資料庫。',
      clearHistory: '清除任務歷史？這將刪除所有已完成和失敗的任務記錄。',
      forceResync: '強制重新同步書籍 {bookId}？這將清除快取並重新取得所有章節。',
      initSync: '<strong>警告：破壞性操作！</strong><br/><br/>此操作將：<br/>• 刪除所有書籍、章節和快取資料<br/>• 從首頁掃描分類<br/>• 將所有發現的書籍加入同步佇列<br/><br/>確定要繼續嗎？',
    },

    // 訊息
    messages: {
      statsRefreshed: '統計資料已更新',
      enqueuedBooks: '已將 {count} 本書加入佇列',
      syncTriggered: '已觸發午夜同步',
      clearedEntries: '已清除 {count} 條記錄',
      cacheCleared: '記憶體快取已清除',
      historyCleared: '已清除 {count} 條任務記錄',
      bookQueued: '書籍已加入重新同步佇列',
      bookAlreadySyncing: '書籍正在同步中',
      enterBookId: '請輸入書籍ID',

      initSyncSuccess: '初始化同步成功：從 {categories} 個分類中加入了 {queued} 本書',
      initSyncFailed: '初始化同步失敗',

      // 錯誤
      fetchStatsFailed: '取得統計資料失敗',
      enqueueFailed: '加入佇列失敗',
      triggerFailed: '觸發同步失敗',
      clearFailed: '清除失敗',
      cacheClearFailed: '清除快取失敗',
      historyClearFailed: '清除任務歷史失敗',
      resyncFailed: '重新同步失敗',
    },

    // SMTP
    smtp: {
      title: 'SMTP 設定',
      host: 'SMTP 主機',
      hostHint: '例如：smtp.gmail.com',
      port: '連接埠',
      portHint: 'TLS 使用 587，SSL 使用 465，一般使用 25',
      user: '使用者名稱',
      userHint: 'SMTP 使用者名稱或電子郵件',
      password: '密碼',
      passwordHint: 'SMTP 密碼或應用程式密碼',
      useTLS: '使用 TLS',
      useSSL: '使用 SSL',
      fromEmail: '寄件人電子郵件',
      fromEmailHint: '留空則使用 SMTP 使用者名稱',
      fromName: '寄件人名稱',
      lastTest: '最後測試',
      testSuccess: '連接成功',
      testFailed: '連接失敗',
      notConfigured: 'SMTP 尚未設定。請先儲存設定。',
      saveSuccess: 'SMTP 設定儲存成功',
      saveFailed: '儲存 SMTP 設定失敗',
    },
  },
};
