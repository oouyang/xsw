// Simplified Chinese (China) translations
export default {
  // 常用
  common: {
    home: '首页',
    settings: '设置',
    chapters: '章节',
    close: '关闭',
    done: '完成',
    cancel: '取消',
    retry: '重试',
    loading: '加载中...',
    error: '错误',
    success: '成功',
  },

  // 导航
  nav: {
    home: '看小说',
    chapters: '目录',
    chapterList: '章节列表',
    prevChapter: '上一章',
    nextChapter: '下一章',
    backToChapterList: '返回章节列表',
    goBack: '返回',
  },

  // 设置
  settings: {
    title: '阅读设置',
    darkMode: '深色模式',
    lightMode: '浅色',
    darkModeLabel: '深色',
    fontSize: '字体大小',
    preview: '预览',
    previewText: '这是阅读界面的预览文字，您可以调整字体大小和深色模式来获得最佳的阅读体验。',
  },

  // 字体大小
  fontSizes: {
    largest: '最大',
    larger: '超大',
    large: '大',
    mediumLarge: '较大',
    medium: '中等',
    small: '较小',
    smallest: '最小',
  },

  // 书籍
  book: {
    author: '作者',
    type: '分类',
    status: '状态',
    updated: '更新',
    lastChapter: '最新章节',
    latestPrefix: '⚡ 最新',
    intro: '简介',
    loadInfoFailed: '加载书籍信息失败',
  },

  // 章节
  chapter: {
    chapter: '章',
    prev: '上一章',
    next: '下一章',
    bypassCache: '略过缓存',
    loadFailed: '加载章节失败',
    loadContentFailed: '加载内容失败',
    loadTimeout: '加载超时，请重试。服务器可能正在处理请求或网络连接缓慢。',
    notFound: '找不到章节',
    readingProgress: '阅读进度',
    displayChapters: '显示第 {start}～{end} 章 (共 {total} 章)',
    noChaptersOnPage: '此页暂无章节',
    loadingChapters: '加载章节中...',
    loadChaptersFailed: '加载章节列表失败',
    reloadChapters: '重新加载',
    loadingFirstPages: '加载前 {pages} 页章节...',
    loadingRemainingInBackground: '后台加载剩余章节...',
    phase2LoadingWarning: '后台加载未完成（前3页已可用）',
    phase2LoadingComplete: '所有章节已加载完成',
    loadingProgress: '已加载 {loaded} / {total} 章',
    estimatedReadingTime: '预计阅读时间',
    readingTimeMinutes: '{minutes} 分钟',
    readingTimeHoursMinutes: '{hours} 小时 {minutes} 分钟',
  },

  // 分类
  category: {
    categories: '分类',
    books: '书籍',
    viewAll: '查看全部',
  },

  // 错误
  error: {
    loadFailed: '加载失败',
    networkError: '网络错误',
    notFound: '404: 找不到',
    serverError: '服务器错误',
  },

  // 动作
  action: {
    scrollTop: '回到顶部',
    scrollBottom: '到达底部',
    goBack: '返回',
    showHeader: '显示标题栏',
  },

  // 搜索
  search: {
    title: '搜索结果',
    placeholder: '搜索书名、作者或内容...',
    keyword: '搜索关键字',
    searching: '搜索中...',
    noResults: '未找到相关结果',
    resultsCount: '找到 {count} 条结果，来自 {books} 本书籍',
    searchFailed: '搜索失败，请稍后再试',
    tabs: {
      all: '全部',
      books: '书籍',
      chapters: '章节',
      content: '内容',
    },
    matchTypes: {
      book_name: '书名',
      author: '作者',
      chapter_title: '章节标题',
      chapter_content: '章节内容',
    },
  },

  // 语言
  language: {
    zhTW: '繁體中文',
    zhCN: '简体中文',
    enUS: 'English',
  },

  // 管理员
  admin: {
    title: '管理面板',
    login: '管理员登录',
    logout: '退出登录',
    username: '用户名',
    password: '密码',
    email: '电子邮件',
    loginButton: '登录',
    loginSuccess: '登录成功',
    loginFailed: '用户名或密码错误',
    logoutSuccess: '已退出登录',

    // Google Sign-In
    googleSignIn: '使用 Google 登录',
    googleSignInFailed: 'Google 登录失败',
    passwordLogin: '密码登录（备用）',
    passwordLoginCaption: '仅供紧急访问使用',

    // 修改密码
    changePassword: '修改密码',
    currentPassword: '当前密码',
    newPassword: '新密码',
    confirmPassword: '确认新密码',
    passwordChanged: '密码修改成功',
    passwordChangeFailed: '密码修改失败',

    // 验证
    allFieldsRequired: '所有字段都是必填的',
    passwordMismatch: '两次输入的新密码不一致',
    passwordTooShort: '密码长度至少为4个字符',
    incorrectPassword: '当前密码不正确',

    // 标签页
    tabs: {
      stats: '统计',
      jobs: '任务',
      cache: '缓存',
      books: '书籍',
      smtp: 'SMTP',
    },

    // 统计
    stats: {
      cache: '缓存统计',
      jobs: '任务统计',
      midnightSync: '午夜同步',
      periodicSync: '定期同步 (6小时)',
      books: '书籍',
      chapters: '章节',
      memory: '内存',
      pending: '待处理',
      completed: '已完成',
      failed: '失败',
      syncing: '同步中',
      total: '总计',
      nextSync: '下次',
      lastSync: '上次',
      interval: '间隔',
      priority: '优先级',
      active: '活跃',
    },

    // 操作
    actions: {
      midnightSync: '午夜同步操作',
      enqueue: '入队',
      trigger: '触发',
      clear: '清理',
      refresh: '刷新',
      clearCache: '清除内存缓存',
      clearHistory: '清除任务历史',
      forceResync: '强制重新同步',
      initSync: '初始化完整同步',
      saveSMTP: '保存设置',
      testSMTP: '测试连接',
    },

    // 提示
    tooltips: {
      enqueue: '将未完成的书籍加入队列',
      trigger: '立即触发同步',
      clear: '清除已完成/失败的记录',
      refresh: '刷新统计数据',
      clearCache: '清除内存缓存（数据库不受影响）',
      clearHistory: '清除已完成和失败的任务记录',
      forceResync: '强制重新同步以修复缺失的章节',
      changePassword: '修改密码',
      initSync: '警告：删除所有数据并从头重新扫描',
    },

    // 书籍管理
    bookManagement: {
      title: '书籍管理',
      bookId: '书籍ID',
      bookIdPlaceholder: '输入要重新同步的书籍ID',
      bookIdHint: '要强制重新同步的书籍ID（例如：1677042）',
    },

    // 初始化同步
    initSync: {
      title: '初始化完整同步',
      categories: '分类数量',
      categoriesHint: '要扫描的分类数量（1-20）',
      pagesPerCategory: '每类页数',
      pagesHint: '每个分类的页数（1-50）',
    },

    // 确认
    confirm: {
      title: '确认',
      clearCache: '清除内存缓存？这不会影响数据库。',
      clearHistory: '清除任务历史？这将删除所有已完成和失败的任务记录。',
      forceResync: '强制重新同步书籍 {bookId}？这将清除缓存并重新获取所有章节。',
      initSync: '<strong>警告：破坏性操作！</strong><br/><br/>此操作将：<br/>• 删除所有书籍、章节和缓存数据<br/>• 从首页扫描分类<br/>• 将所有发现的书籍加入同步队列<br/><br/>确定要继续吗？',
    },

    // 消息
    messages: {
      statsRefreshed: '统计数据已刷新',
      enqueuedBooks: '已将 {count} 本书加入队列',
      syncTriggered: '已触发午夜同步',
      clearedEntries: '已清除 {count} 条记录',
      cacheCleared: '内存缓存已清除',
      historyCleared: '已清除 {count} 条任务记录',
      bookQueued: '书籍已加入重新同步队列',
      bookAlreadySyncing: '书籍正在同步中',
      enterBookId: '请输入书籍ID',

      initSyncSuccess: '初始化同步成功：从 {categories} 个分类中加入了 {queued} 本书',
      initSyncFailed: '初始化同步失败',

      // 错误
      fetchStatsFailed: '获取统计数据失败',
      enqueueFailed: '加入队列失败',
      triggerFailed: '触发同步失败',
      clearFailed: '清除失败',
      cacheClearFailed: '清除缓存失败',
      historyClearFailed: '清除任务历史失败',
      resyncFailed: '重新同步失败',
    },

    // SMTP
    smtp: {
      title: 'SMTP 配置',
      host: 'SMTP 主机',
      hostHint: '例如：smtp.gmail.com',
      port: '端口',
      portHint: 'TLS 使用 587，SSL 使用 465，普通使用 25',
      user: '用户名',
      userHint: 'SMTP 用户名或电子邮件',
      password: '密码',
      passwordHint: 'SMTP 密码或应用密码',
      useTLS: '使用 TLS',
      useSSL: '使用 SSL',
      fromEmail: '发件人邮箱',
      fromEmailHint: '留空则使用 SMTP 用户名',
      fromName: '发件人名称',
      lastTest: '最后测试',
      testSuccess: '连接成功',
      testFailed: '连接失败',
      saveSuccess: 'SMTP 设置保存成功',
      saveFailed: '保存 SMTP 设置失败',
    },
  },
};
