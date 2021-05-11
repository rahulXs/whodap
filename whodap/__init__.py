from .client import DNSClient
from .response import DomainResponse
from .utils import get_dns_client, get_aio_dns_client

__all__ = ['aio_lookup_domain', 'lookup_domain', 'DNSClient']
__version__ = '0.1.0'


def lookup_domain(domain: str, tld: str, cache: bool = True, **kwargs) -> DomainResponse:
    """
    Queries a domain name using RDAP.

    :param domain: the domain name to lookup
    :param tld: the top level domain
    :param cache: if True, attempt to use a cached DNSClient
    :param kwargs: parameters passed directly to `httpx.Client`
    :return: an instance of DomainResponse
    """
    if cache:
        client = get_dns_client(**kwargs)
    else:
        client = DNSClient.new_client(**kwargs)
    return client.lookup(domain, tld)


async def aio_lookup_domain(domain: str, tld: str, cache: bool = True, **kwargs) -> DomainResponse:
    """
    Queries a domain name using RDAP (asyncio compatible).

    :param domain: the domain name to lookup
    :param tld: the top level domain
    :param cache: if True, attempt to use a cached DNSClient
    :param kwargs: parameters passed directly to `httpx.AsyncClient`
    :return: an instance of DomainResponse
    """
    if cache:
        client = get_aio_dns_client(**kwargs)
    else:
        client = await DNSClient.new_aio_client(**kwargs)
    return await client.aio_lookup(domain, tld)