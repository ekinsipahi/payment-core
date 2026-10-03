def client_ip(request):
    """The real client IP behind common proxies (Render / Netlify / Cloudflare).

    ``REMOTE_ADDR`` on these platforms is the INTERNAL load-balancer address (a
    private 10.x IP), never the visitor — so it must not be used as the client
    IP.

    Preference order:
    1. ``CF-Connecting-IP`` — set by Cloudflare at the edge from its own TCP
       connection to the visitor; a client CANNOT forge this (Cloudflare
       overwrites whatever the client sends before it reaches origin). Only
       present when the backend sits behind Cloudflare.
    2. The left-most entry of ``X-Forwarded-For`` — correct for a backend that
       sits directly behind Render/Netlify's edge, but client-suppliable and
       therefore spoofable on any edge that doesn't strip it first. A light risk
       signal, not an auth control.
    3. ``REMOTE_ADDR`` as the last resort.

    Checking CF-Connecting-IP first is a no-op when not behind Cloudflare (the
    header is simply absent), so this is safe to use on any deployment unchanged.
    """
    if request is None:
        return None
    cf = request.META.get("HTTP_CF_CONNECTING_IP", "")
    if cf:
        return cf.strip()
    xff = request.META.get("HTTP_X_FORWARDED_FOR", "")
    if xff:
        first = xff.split(",")[0].strip()
        if first:
            return first
    return request.META.get("REMOTE_ADDR")
