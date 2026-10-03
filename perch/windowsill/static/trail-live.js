/* The live scentTrail's one piece of own script (ADR 0011). Leaving /trail aborts the event stream, and htmx
   logs every aborted stream as a console error; closing the stream first leaves nothing to log. It closes the
   EventSource htmx-ext-sse keeps on the element (htmx 2.0.11 and htmx-ext-sse 2.2.4, both pinned, store it in the
   element's 'htmx-internal-data'); if that ever moves, the stream simply isn't closed early. No eval, no network. */
(function () {
  function closeStream() {
    var live = document.querySelector('[sse-connect]');
    var data = live && live['htmx-internal-data'];
    if (data && data.sseEventSource) { data.sseEventSource.close(); }
  }
  window.addEventListener('beforeunload', closeStream);
  window.addEventListener('pagehide', closeStream);
})();
