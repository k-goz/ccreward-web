import json

# 读取数据
with open('data.json', 'r', encoding='utf-8') as f:
    data = json.load(f)

# 读取原 index.html
with open('index.html', 'r', encoding='utf-8') as f:
    html = f.read()

# 1. 插入 DATA 常量
data_js = '<script>\nconst DATA = ' + json.dumps(data, ensure_ascii=False) + ';\n</script>\n'

# 2. 替换 init 块 — 用 DATA 而非 fetch
old_init = """(async function init() {
  try {
    const [ov,cats,cds] = await Promise.all([
      get('/cards/stats/overview'),
      get('/activities/categories'),
      get('/cards?page_size=100'),
    ]);
    S.overview = ov; S.categories = cats;
    S.cards = cds.items || cds;
    S.cards.forEach(c=>{ c.benefits=c.benefits||[]; S.cardsById[c.id]=c; });
    document.getElementById('hdr-cards').innerHTML = `📊 ${ov.cards}卡`;
    document.getElementById('hdr-banks').innerHTML = `🏦 ${ov.banks}行`;
    document.getElementById('hdr-activities').innerHTML = `🎫 ${ov.activities||'?'}活动`;
  } catch(e) { console.error(e); }

  document.querySelectorAll('.tab').forEach(el=>el.addEventListener('click',()=>{
    document.querySelectorAll('.tab').forEach(x=>x.classList.remove('active'));
    el.classList.add('active');
    S.tab = el.dataset.tab;
    render();
  }));
  render();
})();"""

new_init = """(function init() {
  try {
    const ov = DATA.stats;
    const cats = DATA.categories;
    const cds = { items: DATA.cards };
    S.overview = ov; S.categories = cats;
    S.cards = cds.items || cds;
    S.cards.forEach(c=>{ c.benefits=c.benefits||[]; S.cardsById[c.id]=c; });
    document.getElementById('hdr-cards').innerHTML = '📊 ' + ov.cards + '卡';
    document.getElementById('hdr-banks').innerHTML = '🏦 ' + ov.banks + '行';
    document.getElementById('hdr-activities').innerHTML = '🎫 ' + (ov.activities||'?') + '活动';
  } catch(e) { console.error(e); }

  document.querySelectorAll('.tab').forEach(el=>el.addEventListener('click',()=>{
    document.querySelectorAll('.tab').forEach(x=>x.classList.remove('active'));
    el.classList.add('active');
    S.tab = el.dataset.tab;
    render();
  }));
  render();
})();"""

html = html.replace(old_init, new_init)

# 3. 替换 doSearch — 本地搜索
old_search = """async function doSearch() {
  const kw = document.getElementById('searchInput').value.trim();
  const el = document.getElementById('deals-result');
  if(!kw){ el.innerHTML='<div class="empty">请输入搜索关键词</div>'; return; }
  el.innerHTML='<div class="loading">⏳ 搜索中...</div>';
  try {
    S.searchResult = await get(`/activities/compare?keyword=${encodeURIComponent(kw)}`);
    renderDealsResult();
  } catch(e) { el.innerHTML=`<div class="empty">搜索失败: ${esc(e.message)}</div>`; }
}"""

new_search = """function doSearch() {
  const kw = document.getElementById('searchInput').value.trim();
  const el = document.getElementById('deals-result');
  if(!kw){ el.innerHTML='<div class="empty">请输入搜索关键词</div>'; return; }
  el.innerHTML='<div class="loading">⏳ 搜索中...</div>';
  // 本地搜索
  const kwLower = kw.toLowerCase();
  const items = DATA.activities.filter(a => {
    const text = ((a.title||'') + (a.merchant_name||'') + (a.product_name||'') + (a.category||'')).toLowerCase();
    return text.includes(kwLower);
  }).sort((a,b) => (a.activity_price||999) - (b.activity_price||999));
  // 标记最低价
  const cheapestPrice = items.length && items[0].activity_price ? items[0].activity_price : null;
  const platforms = [...new Set(items.map(i => i.platform))];
  const result = {
    keyword: kw,
    items: items.map(i => ({
      title: i.title,
      platform: i.platform,
      platform_label: i.platform,
      activity_price: i.activity_price,
      original_price: i.original_price,
      discount_description: i.discount_description,
      usage_conditions: i.usage_conditions,
      source_url: i.source_url,
      app_url: i.app_url,
      is_cheapest: cheapestPrice && i.activity_price === cheapestPrice,
    })),
    cheapest_price: cheapestPrice,
    cheapest_platform: cheapestPrice ? items[0].platform : null,
    total_platforms: platforms.length,
  };
  S.searchResult = result;
  renderDealsResult();
}"""

html = html.replace(old_search, new_search)

# 4. 替换 loadActivities — 本地数据
old_load = """async function loadActivities() {
  try {
    const r = await get('/activities?page_size=100&sort=price');
    S.activities = r.items || [];
    renderActivityFilters();
    renderActivityList();
  } catch(e) { document.getElementById('act-list').innerHTML=`<div class="empty">加载失败: ${esc(e.message)}</div>`; }
}"""

new_load = """function loadActivities() {
  S.activities = DATA.activities.slice().sort((a,b) => (a.activity_price||999) - (b.activity_price||999));
  renderActivityFilters();
  renderActivityList();
}"""

html = html.replace(old_load, new_load)

# 5. 替换 redemptions fetch — 本地数据
old_redemptions = """  get(`/cards/${vc.id}/redemptions`).then(items=>{
    document.getElementById('redemptions-area').innerHTML = items.length ? items.map(r=>`<div class="redemption-item"><div class="redemption-info"><h4>${esc(r.item_name)}</h4><p>${esc(r.merchant_name)} · ${esc(r.category)}</p></div><div class="redemption-right"><div class="redemption-points">${r.points_required}积分</div>${r.cash_value?`<div class="redemption-value">≈¥${r.cash_value}</div>`:''}</div></div>`).join('') : '<div class="empty">暂无兑换商品</div>';
  }).catch(()=>{ document.getElementById('redemptions-area').innerHTML='<div class="empty">加载失败</div>'; });"""

new_redemptions = """  { const items = vc.redemptions || [];
    document.getElementById('redemptions-area').innerHTML = items.length ? items.map(r=>'<div class="redemption-item"><div class="redemption-info"><h4>'+esc(r.item_name)+'</h4><p>'+esc(r.merchant_name)+' · '+esc(r.category)+'</p></div><div class="redemption-right"><div class="redemption-points">'+r.points_required+'积分</div>'+(r.cash_value?'<div class="redemption-value">≈¥'+r.cash_value+'</div>':'')+'</div></div>').join('') : '<div class="empty">暂无兑换商品</div>';
  }"""

html = html.replace(old_redemptions, new_redemptions)

# 插入 DATA 常量到 </body> 之前
html = html.replace('</body>', data_js + '</body>')

with open('static.html', 'w', encoding='utf-8') as f:
    f.write(html)

print(f'Static HTML: {len(html)} bytes ({len(html)/1024:.1f} KB)')
