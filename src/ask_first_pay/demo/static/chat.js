/* Chat page: the conversation scrolls inside its own box, newest message in view, so the
   "what just happened" line at the top of the page stays visible after every action.
   Without JS the #end anchor still jumps to the newest message. */
(function () {
  var list = document.querySelector('.chat');
  if (!list) return;
  function settle() {
    list.scrollTop = list.scrollHeight;
    if (location.hash === '#end') { window.scrollTo(0, 0); }
  }
  settle();
  window.addEventListener('load', function () { setTimeout(settle, 0); });
})();
