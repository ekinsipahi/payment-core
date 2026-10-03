def client_ip(request):
    """The real client IP behind the proxies (Render / Netlify / Cloudflare).

    ``REMOTE_ADDR`` on these platforms is the INTERNAL load-balancer address (a
    private 10.x IP), never the visitor — so it must not be used as the client
    IP. The original client is the left-most entry of ``X-Forwarded-For``.

    Note: the left-most XFF entry is client-supplied and therefore spoofable;
    this is a light risk signal, not an auth control. Behind Cloudflare prefer
    ``CF-Connecting-IP``; set PAYGUARD so you trust the right header for your
    edge. (Kept header-simple here to match the Sterr backends' existing util.)
    """
    if request is None:
        return None
    xff = request.META.get("HTTP_X_FORWARDED_FOR", "")
    if xff:
        first = xff.split(",")[0].strip()
        if first:
            return first
    return request.META.get("REMOTE_ADDR")
