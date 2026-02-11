"""HTML fixture constants for czbooks.net test data."""

CZBOOKS_HOMEPAGE_HTML = """\
<html><body>
<ul class="nav menu">
  <li><a href="//czbooks.net/c/xuanhuan">玄幻</a></li>
  <li><a href="//czbooks.net/c/yanqing">言情</a></li>
  <li><a href="//czbooks.net/c/xuanhuan">玄幻</a></li>
</ul>
</body></html>
"""

CZBOOKS_CATEGORY_PAGE_HTML = """\
<html><body>
<li class="novel-item-wrapper">
  <div class="novel-item">
    <div class="novel-item-cover-wrapper">
      <a href="//czbooks.net/n/book1">
        <div class="novel-item-title">第一本書</div>
      </a>
    </div>
    <div class="novel-item-author"><a href="/a/auth1">作者一</a></div>
    <div class="novel-item-newest-chapter"><a href="//czbooks.net/n/book1/ch99">第99章</a></div>
  </div>
</li>
<li class="novel-item-wrapper">
  <div class="novel-item">
    <div class="novel-item-cover-wrapper">
      <a href="//czbooks.net/n/book2">
        <div class="novel-item-title">第二本書</div>
      </a>
    </div>
    <div class="novel-item-author"><a href="/a/auth2">作者二</a></div>
    <div class="novel-item-newest-chapter"><a href="//czbooks.net/n/book2/ch50">第50章</a></div>
  </div>
</li>
</body></html>
"""

CZBOOKS_BOOK_DETAIL_HTML = """\
<html><body>
<div class="novel-detail">
  <div class="info">
    <div class="title">《測試小說》</div>
    <div class="author"><a href="/a/testauthor">測試作者</a></div>
  </div>
  <div class="state">
    <table><tr>
      <td>狀態：</td><td>連載中</td>
      <td>更新：</td><td>2026-02-01</td>
    </tr></table>
  </div>
  <a id="novel-category" href="/c/xuanhuan">玄幻</a>
  <div class="description">這是一本測試小說。</div>
</div>
<ul class="chapter-list">
  <li class="volume">第一卷 起始</li>
  <li><a href="//czbooks.net/n/testbook/ch1">第1章 開始</a></li>
  <li><a href="//czbooks.net/n/testbook/ch2">第2章 發展</a></li>
  <li><a href="//czbooks.net/n/testbook/ch3">第3章 結局</a></li>
</ul>
</body></html>
"""

CZBOOKS_CHAPTER_DETAIL_HTML = """\
<html><body>
<div class="chapter-detail">
  <div class="name">第1章 開始</div>
  <div class="content">這是第一章的內容。故事從這裡開始了。</div>
</div>
</body></html>
"""
