import posixpath
from abc import ABC, abstractmethod
from typing import Dict, Any, Union

import httpx

from .codes import RDAPStatusCodes
from .errors import RateLimitError, NotFoundError, MalformedQueryError
from .response import DomainResponse


class RDAPClient(ABC):

    _iana_publication_key: str = 'publication'
    _iana_verison_key: str = 'version'

    def __init__(self, *args, **kwargs):
        self._session: Union[httpx.Client, httpx.AsyncClient] = None
        self.version: str
        self.publication: str

    @classmethod
    @abstractmethod
    def new_client(cls):
        ...

    @classmethod
    @abstractmethod
    async def new_aio_client(cls):
        ...

    @abstractmethod
    def lookup(self):
        ...

    @abstractmethod
    async def aio_lookup(self):
        ...

    @abstractmethod
    def _load_from_iana(self):
        ...

    @abstractmethod
    async def _aio_load_from_iana(self):
        ...

    @staticmethod
    @abstractmethod
    def _build_query_uri() -> str:
        ...

    def _get_request(self, uri: str) -> httpx.Response:
        with self._session as client:
            return client.get(uri)

    async def _aio_get_request(self, uri: str) -> httpx.Response:
        async with self._session as client:
            return await client.get(uri)

    @staticmethod
    def _check_status_code(status_code: int) -> None:
        if status_code == RDAPStatusCodes.POSITIVE_ANSWER_200:
            return
        elif status_code == RDAPStatusCodes.MALFORMED_QUERY_400:
            raise MalformedQueryError(
                f"Malformed query: {RDAPStatusCodes.MALFORMED_QUERY_400} response from server")
        elif status_code == RDAPStatusCodes.NEGATIVE_ANSWER_404:
            raise NotFoundError(
                f"Domain not found: {RDAPStatusCodes.NEGATIVE_ANSWER_404} response from server")
        elif status_code == RDAPStatusCodes.RATE_LIMIT_429:
            raise RateLimitError(
                f"Too many requests: {RDAPStatusCodes.RATE_LIMIT_429} response from server")
        else:
            raise


class DNSClient(RDAPClient):

    # IANA DNS
    _iana_dns_json_uri: str = 'https://data.iana.org/rdap/dns.json'
    _iana_dns_services_key: str = 'services'

    def __init__(self):
        super(DNSClient, self).__init__()
        self.iana_dns_server_map: Dict[str, str] = {}

    @classmethod
    def new_client(cls, **kwargs):
        """
        Primary method of instantiating a synchronous instance of DNSClient

        :kwargs: keyword arguments passed directly to `httpx.Client`
        :return: a DNSClient
        """
        c = cls()
        c._session = httpx.Client(**kwargs)
        dns = c._load_from_iana()
        c._set_iana_dns_info(dns)
        return c

    @classmethod
    async def new_aio_client(cls, **kwargs):
        """
        Primary method of instantiating an asynchronous instance of DNSClient

        :kwargs: keyword arguments passed directly to `httpx.AsyncClient`
        :return: a DNSClient
        """
        c = cls()
        c._session = httpx.AsyncClient(**kwargs)
        dns = await c._aio_load_from_iana()
        c._set_iana_dns_info(dns)
        return c

    @staticmethod
    def _build_query_uri(rdap_uri: str, domain: str) -> str:
        return posixpath.join(rdap_uri, 'domain', domain)

    def lookup(self, domain: str, tld: str, auth_ref: str = None) -> DomainResponse:
        domain_and_tld = domain + '.' + tld
        # if an authoritative url is provided; use it
        if auth_ref:
            query_url = self._build_query_uri(auth_ref, domain_and_tld)
            resp = self._get_request(query_url)
            self._check_status_code(resp.status_code)
            return DomainResponse.from_json(resp.text)
        # start with looking up server in the IANA list
        iana_url = self.iana_dns_server_map.get(tld)
        if not iana_url:
            raise NotImplementedError(f'RDAP for {tld} is not supported')
        # hit the server found in the IANA list
        query_url = self._build_query_uri(iana_url, domain_and_tld)
        print(query_url)
        response = self._get_request(query_url)
        self._check_status_code(response.status_code)
        domain_response = DomainResponse.from_json(response.text)
        # try to extract an authoritative server for this domain
        if hasattr(domain_response, 'links'):
            authority_url = domain_response.links[-1].href
            print(authority_url)
            # avoid redundant connections
            if authority_url.lower() != query_url.lower():
                resp = self._get_request(authority_url)
                self._check_status_code(resp.status_code)
                return DomainResponse.from_json(resp.text)
            else:
                return domain_response
        else:
            return domain_response

    async def aio_lookup(self, domain: str, tld: str, auth_ref: str = None) -> DomainResponse:
        domain_and_tld = domain + '.' + tld
        if auth_ref:
            query_url = self._build_query_uri(auth_ref, domain_and_tld)
            resp = await self._aio_get_request(query_url)
            self._check_status_code(resp.status_code)
            return DomainResponse.from_json(resp.read())

        iana_url = self.iana_dns_server_map.get(tld)
        if not iana_url:
            raise NotImplementedError(f'RDAP for {tld} is not supported')

        query_url = self._build_query_uri(iana_url, domain_and_tld)
        response = await self._aio_get_request(query_url)
        self._check_status_code(response.status_code)
        domain_response = DomainResponse.from_json(response.read())
        if hasattr(domain_response, 'links'):
            authority_url = domain_response.links[-1].href
            if authority_url.lower() != query_url.lower():
                resp = await self._aio_get_request(authority_url)
                self._check_status_code(resp.status_code)
                return DomainResponse.from_json(resp.read())
            else:
                return domain_response
        else:
            return domain_response

    async def _aio_load_from_iana(self):
        resp = await self._aio_get_request(self._iana_dns_json_uri)
        if resp.status_code != httpx.codes.OK:
            raise ConnectionError(f"Bad response from {self._iana_dns_json_uri}")
        return resp.json()

    def _load_from_iana(self):
        resp = self._get_request(self._iana_dns_json_uri)
        if resp.status_code != httpx.codes.OK:
            raise ConnectionError(f"Bad response from {self._iana_dns_json_uri}")
        return resp.json()

    def _set_iana_dns_info(self, iana_dns_map: Dict[str, Any]) -> None:
        self.publication = iana_dns_map.get(self._iana_publication_key)
        self.version = iana_dns_map.get(self._iana_verison_key)
        tld_server_map = {}
        for tlds, server in iana_dns_map.get(self._iana_dns_services_key):
            for tld in tlds:
                tld_server_map[tld] = server[0]
        self.iana_dns_server_map = tld_server_map


class IPv4Client(RDAPClient):

    # IANA IPv4
    ...

    @classmethod
    def new_client(cls):
        ...

    @classmethod
    async def new_aio_client(cls):
        ...

    def lookup(self):
        ...

    async def aio_lookup(self):
        ...

    def _load_from_iana(self):
        ...

    async def _aio_load_from_iana(self):
        ...

    @staticmethod
    def _build_query_uri() -> str:
        ...


class IPv6Client(RDAPClient):

    # IANA IPv6
    ...

    @classmethod
    def new_client(cls):
        ...

    @classmethod
    async def new_aio_client(cls):
        ...

    def lookup(self):
        ...

    async def aio_lookup(self):
        ...

    def _load_from_iana(self):
        ...

    async def _aio_load_from_iana(self):
        ...

    @staticmethod
    def _build_query_uri() -> str:
        ...


class ASNClient(RDAPClient):

    # IANA ASN
    ...

    @classmethod
    def new_client(cls):
        ...

    @classmethod
    async def new_aio_client(cls):
        ...

    def lookup(self):
        ...

    async def aio_lookup(self):
        ...

    def _load_from_iana(self):
        ...

    async def _aio_load_from_iana(self):
        ...

    @staticmethod
    def _build_query_uri() -> str:
        ...