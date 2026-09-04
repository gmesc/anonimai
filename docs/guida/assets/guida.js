/* Guida ZAINO — indice navigabile (scrollspy), lightbox, tema, sidebar mobile */
(function(){
  var root = document.documentElement;

  /* ---- tema chiaro/scuro (ricordato) ---- */
  var salvato = null;
  try { salvato = localStorage.getItem('guida.tema'); } catch(e){}
  if (salvato) root.setAttribute('data-theme', salvato);
  var tt = document.getElementById('temaBtn');
  if (tt) tt.addEventListener('click', function(){
    var scuro = root.getAttribute('data-theme') === 'scuro' ||
      (!root.getAttribute('data-theme') && matchMedia('(prefers-color-scheme: dark)').matches);
    var nuovo = scuro ? 'chiaro' : 'scuro';
    root.setAttribute('data-theme', nuovo);
    try { localStorage.setItem('guida.tema', nuovo); } catch(e){}
  });

  /* ---- sidebar su schermi stretti ---- */
  var mb = document.getElementById('menuBtn');
  if (mb) mb.addEventListener('click', function(){
    root.setAttribute('data-nav', root.getAttribute('data-nav') === 'open' ? '' : 'open');
  });
  document.querySelectorAll('.toc a').forEach(function(a){
    a.addEventListener('click', function(){ root.setAttribute('data-nav', ''); });
  });

  /* ---- indice: costruito dai titoli, con scrollspy ---- */
  var toc = document.getElementById('toc');
  var sezioni = Array.prototype.slice.call(document.querySelectorAll('section.cap'));
  if (toc) {
    sezioni.forEach(function(sec){
      var h2 = sec.querySelector('h2'); if (!h2) return;
      var li = document.createElement('li');
      var a = document.createElement('a'); a.href = '#' + sec.id; a.textContent = h2.textContent;
      li.appendChild(a);
      var h3s = sec.querySelectorAll('h3[id]');
      if (h3s.length) {
        var ul = document.createElement('ul');
        h3s.forEach(function(h3){
          var l2 = document.createElement('li'); var a2 = document.createElement('a');
          a2.href = '#' + h3.id; a2.textContent = h3.textContent; l2.appendChild(a2); ul.appendChild(l2);
        });
        li.appendChild(ul);
      }
      toc.appendChild(li);
    });
    var voci = Array.prototype.slice.call(toc.querySelectorAll('li'));
    function accendi(){
      var y = window.scrollY + 120;
      var capAttivo = null, subAttivo = null;
      sezioni.forEach(function(sec){ if (sec.offsetTop <= y) capAttivo = sec; });
      if (capAttivo) {
        var h3s = capAttivo.querySelectorAll('h3[id]');
        h3s.forEach(function(h){ if (h.offsetTop <= y) subAttivo = h; });
      }
      voci.forEach(function(li){
        var a = li.querySelector(':scope > a'); if (!a) return;
        var id = a.getAttribute('href').slice(1);
        var on = (capAttivo && id === capAttivo.id) || (subAttivo && id === subAttivo.id);
        li.classList.toggle('attivo', !!on);
      });
      var att = toc.querySelector('li.attivo > a');
      if (att && toc.parentElement) {
        var r = att.getBoundingClientRect(), s = toc.parentElement.getBoundingClientRect();
        if (r.top < s.top + 20 || r.bottom > s.bottom - 20) att.scrollIntoView({ block: 'center' });
      }
    }
    var tick = false;
    window.addEventListener('scroll', function(){ if (!tick) { tick = true; requestAnimationFrame(function(){ accendi(); tick = false; }); } });
    accendi();
    window.addEventListener('hashchange', function(){ setTimeout(accendi, 50); });
    window.addEventListener('load', function(){ setTimeout(accendi, 50); });
  }

  /* ---- lightbox ---- */
  var lb = document.getElementById('lb');
  var lbImg = lb && lb.querySelector('img');
  var lbCap = lb && lb.querySelector('figcaption');
  var imgs = Array.prototype.slice.call(document.querySelectorAll('figure img'));
  var cur = -1;
  function apri(i){
    if (!lb || !imgs[i]) return;
    cur = i;
    lbImg.src = imgs[i].getAttribute('src');
    lbImg.alt = imgs[i].alt || '';
    var fc = imgs[i].closest('figure') && imgs[i].closest('figure').querySelector('figcaption');
    lbCap.textContent = fc ? fc.textContent : (imgs[i].alt || '');
    lb.classList.add('aperto');
    document.body.style.overflow = 'hidden';
  }
  function chiudi(){ if (!lb) return; lb.classList.remove('aperto'); document.body.style.overflow = ''; cur = -1; }
  imgs.forEach(function(im, i){
    im.setAttribute('tabindex', '0'); im.setAttribute('role', 'button');
    im.addEventListener('click', function(){ apri(i); });
    im.addEventListener('keydown', function(e){ if (e.key === 'Enter' || e.key === ' ') { e.preventDefault(); apri(i); } });
  });
  if (lb) {
    lb.addEventListener('click', function(e){ if (e.target === lb) chiudi(); });
    lb.querySelector('.lbx').addEventListener('click', chiudi);
    lb.querySelector('.lbp').addEventListener('click', function(e){ e.stopPropagation(); apri((cur - 1 + imgs.length) % imgs.length); });
    lb.querySelector('.lbn').addEventListener('click', function(e){ e.stopPropagation(); apri((cur + 1) % imgs.length); });
    document.addEventListener('keydown', function(e){
      if (!lb.classList.contains('aperto')) return;
      if (e.key === 'Escape') chiudi();
      if (e.key === 'ArrowLeft') apri((cur - 1 + imgs.length) % imgs.length);
      if (e.key === 'ArrowRight') apri((cur + 1) % imgs.length);
    });
  }
})();
