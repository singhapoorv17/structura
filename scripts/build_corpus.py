"""Build a corpus file from a compact table of verified transactions.

Each row below was confirmed against the source named in it. The expansion
below is mechanical: it turns a compact row into the full provenanced record
the loader expects, and fills every field the source did not carry with an
explicit not-disclosed cell rather than leaving it blank.

Run:  python scripts/build_corpus.py
"""

from __future__ import annotations

import json
import pathlib

OUT = pathlib.Path(__file__).resolve().parent.parent / "comps" / "data" / "deals-2026.json"

#: Default reason for a field this entry does not carry. Phrased for what is
#: actually true: the entry was built from one source, and that source did not
#: state it. It does not claim the fact is unknowable.
NR = "Not stated in the source recorded for this entry."

#: Pricing is the field that is almost never disclosed on a project financing.
NO_PRICE = "No spread, coupon or fee was disclosed."
NO_TENOR = "No tenor was disclosed."


def S(value, src, url, date, unit="", note=""):
    """A stated cell. ``date=None`` records that the date was not captured."""
    out = {
        "value": value,
        "provenance": "stated",
        "source": src,
        "source_url": url,
    }
    if date is None:
        out["source_date"] = None
        out["source_date_unknown"] = True
    else:
        out["source_date"] = date
    if unit:
        out["unit"] = unit
    if note:
        out["note"] = note
    return out


def ND(reason=NR):
    return {"provenance": "not_disclosed", "reason": reason}


def tranche(name, kind, amount=None, pricing=None, tenor=None, note=""):
    return {
        "name": name,
        "kind": kind,
        "amount": amount or ND("The breakdown did not give a size for this facility."),
        "pricing": pricing or ND(NO_PRICE),
        "tenor_years": tenor or ND(NO_TENOR),
        "note": note,
    }


# ---------------------------------------------------------------------------
# Sources
# ---------------------------------------------------------------------------

MERCOM = "Mercom Capital, Project Finance Brief"
PVMAG = "pv magazine USA"
ESN = "Energy-Storage.news"
DCD = "DataCenterDynamics"
IFR = "IFR"
SEC = "US SEC, EDGAR"
AXIOS = "Axios"


def build():
    deals = []

    def add(
        key,
        name,
        technology,
        *,
        src,
        url,
        date,
        sponsor,
        quantum=None,
        close=None,
        cod=None,
        location=None,
        capacity=None,
        contract="UNKNOWN",
        offtake=None,
        credit=None,
        lenders=(),
        tranches=(),
        headline="",
        summary="",
        tags=(),
    ):
        def cell(v, unit="", note=""):
            return S(v, src, url, date, unit=unit, note=note) if v is not None else ND()

        deals.append(
            {
                "key": key,
                "name": name,
                "technology": technology,
                "contract_kind": contract,
                "headline": headline,
                "summary": summary,
                "primary_source": src,
                "tags": list(tags),
                "sponsor": cell(sponsor),
                "total_quantum": cell(quantum, unit="USD"),
                "close_date": cell(close),
                "cod": cell(cod),
                "location": cell(location),
                "capacity": cell(capacity),
                "offtake": offtake if isinstance(offtake, dict) else cell(offtake),
                "credit_route": credit if isinstance(credit, dict) else cell(credit),
                "lenders": list(lenders),
                "tranches": list(tranches),
            }
        )

    def amt(v, src, url, date, note=""):
        return S(v, src, url, date, unit="USD", note=note)

    # -- solar and solar + storage -----------------------------------------

    u = "https://pv-magazine-usa.com/2026/03/24/doral-renewables-closes-900-million-financing-for-texas-solar-plus-storage-project/"
    add(
        "doral-cold-creek-2026",
        "Doral Renewables, Cold Creek solar and storage",
        "SOLAR_PLUS_STORAGE",
        src=PVMAG,
        url=u,
        date="2026-03-24",
        sponsor="Doral Renewables",
        quantum=900_000_000,
        close="2026-03",
        cod="Summer 2028",
        location="Tom Green and Schleicher Counties, Texas",
        capacity="430 MWac solar with 340 MWh battery storage",
        credit="$360 million production tax credit transfer agreement",
        lenders=["MUFG (lead)", "Santander", "HSBC", "Ally", "IDB"],
        headline="Doral Renewables closes $900 million financing for Cold Creek",
        tags=["ercot", "ptc-transfer", "construction-to-term"],
        tranches=[
            tranche(
                "construction-to-term",
                "CONSTRUCTION_TO_TERM",
                amt(400_000_000, PVMAG, u, "2026-03-24", note="Reported as more than $400 million."),
            ),
            tranche("tax equity bridge", "TAX_EQUITY_BRIDGE", amt(35_000_000, PVMAG, u, "2026-03-24")),
            tranche("letters of credit", "LETTER_OF_CREDIT", amt(55_000_000, PVMAG, u, "2026-03-24")),
        ],
    )

    u = "https://pv-magazine-usa.com/2026/05/15/sunraycer-renewables-closes-901-million-financing-for-473-mwh-bess-portfolio-in-texas/"
    add(
        "sunraycer-2026",
        "Sunraycer Renewables, three-project Texas portfolio",
        "SOLAR_PLUS_STORAGE",
        src=PVMAG,
        url=u,
        date="2026-05-15",
        sponsor="Sunraycer Renewables",
        quantum=901_000_000,
        close="2026-05",
        location="Texas",
        capacity="479.5 MWac solar with 236.5 MW / 473 MWh battery storage",
        credit="Tax credit bridge within the facility",
        lenders=["MUFG", "Ally", "Nomura", "Nord/LB", "Societe Generale"],
        headline="Sunraycer closes $901 million for a three-project Texas portfolio",
        tags=["ercot", "portfolio"],
        tranches=[
            tranche("construction-to-term", "CONSTRUCTION_TO_TERM"),
            tranche("tax credit bridge", "TRANSFER_BRIDGE"),
            tranche("letters of credit", "LETTER_OF_CREDIT"),
        ],
    )

    u = "https://pv-magazine-usa.com/2026/06/26/matrix-renewables-secures-1-3-billion-for-u-s-solar-and-storage-portfolio/"
    add(
        "matrix-renewables-2026",
        "Matrix Renewables, US solar and storage portfolio",
        "SOLAR_PLUS_STORAGE",
        src=PVMAG,
        url=u,
        date="2026-06-26",
        sponsor="Matrix Renewables",
        quantum=1_300_000_000,
        close="2026-06",
        location="United States",
        capacity="859 MWdc solar and 167 MWh storage",
        credit="Tax equity bridge within the facility",
        headline="Matrix Renewables secures $1.3 billion for a US solar and storage portfolio",
        tags=["portfolio", "preferred-equity"],
        tranches=[
            tranche("construction-to-term", "CONSTRUCTION_TO_TERM", amt(470_000_000, PVMAG, u, "2026-06-26")),
            tranche("tax equity bridge", "TAX_EQUITY_BRIDGE", amt(400_000_000, PVMAG, u, "2026-06-26", note="Reported as approximately $400 million.")),
            tranche("letters of credit", "LETTER_OF_CREDIT", amt(100_000_000, PVMAG, u, "2026-06-26")),
            tranche("preferred equity", "PREFERRED"),
        ],
    )

    u = "https://pv-magazine-usa.com/2026/06/30/enlight-raises-2-6-billion-for-co-bar-solar-and-bess-complex-reaches-financial-close/"
    add(
        "enlight-co-bar-2026",
        "Enlight Renewable Energy, CO Bar solar and storage complex",
        "SOLAR_PLUS_STORAGE",
        src=PVMAG,
        url=u,
        date="2026-06-30",
        sponsor="Enlight Renewable Energy",
        quantum=2_600_000_000,
        close="2026-06",
        credit="Tax equity proceeds of roughly $1.5 billion",
        headline="Enlight raises $2.6 billion for the CO Bar complex and reaches financial close",
        tags=["tax-equity", "large-cap"],
        tranches=[
            tranche("term loan", "TERM_LOAN", amt(1_700_000_000, PVMAG, u, "2026-06-30")),
            tranche("tax equity", "TAX_EQUITY", amt(1_500_000_000, PVMAG, u, "2026-06-30", note="Reported as roughly $1.5 billion of proceeds.")),
        ],
    )

    u = "https://pv-magazine-usa.com/2026/02/11/greenbacker-secures-440-million-tax-equity-for-new-yorks-largest-solar-project/"
    add(
        "greenbacker-cider-2026",
        "Greenbacker, Cider Solar tax equity",
        "SOLAR",
        src=PVMAG,
        url=u,
        date="2026-02-11",
        sponsor="Greenbacker Renewable Energy",
        quantum=440_000_000,
        close="2026-02",
        cod="Late 2026",
        location="New York",
        capacity="674 MWdc / 500 MWac",
        credit="Tax equity commitment",
        lenders=["U.S. Bank", "M&T Bank"],
        headline="Greenbacker secures $440 million tax equity for Cider Solar",
        tags=["tax-equity", "new-york"],
        tranches=[tranche("tax equity", "TAX_EQUITY", amt(440_000_000, PVMAG, u, "2026-02-11"))],
    )

    u = "https://mercomcapital.com/project-finance-brief-dimension-closes-650m-solar-project-financing/"
    add(
        "dimension-energy-2026",
        "Dimension Energy, community solar portfolio",
        "SOLAR",
        src=MERCOM,
        url=u,
        date="2026-04-08",
        sponsor="Dimension Energy",
        quantum=650_000_000,
        close="2026-04",
        capacity="25 community solar projects, 132 MW combined",
        credit="Tax equity within the package",
        headline="Dimension Energy closes $650 million construction and term financing",
        tags=["community-solar", "portfolio"],
        tranches=[
            tranche("debt financing", "CONSTRUCTION_TO_TERM", amt(415_000_000, MERCOM, u, "2026-04-08")),
            tranche("tax equity", "TAX_EQUITY", amt(235_000_000, MERCOM, u, "2026-04-08")),
        ],
    )

    u = "https://pv-magazine-usa.com/2026/07/22/avantus-completes-aratina-1-secures-phase-2-financing-targets-952-mwh-of-solar-charged-storage/"
    add(
        "avantus-aratina-p2-2026",
        "Avantus, Aratina phase 2",
        "SOLAR_PLUS_STORAGE",
        src=PVMAG,
        url=u,
        date="2026-07-22",
        sponsor="Avantus",
        quantum=525_000_000,
        close="2026-07",
        capacity="Targeting 952 MWh of solar-charged storage across the programme",
        credit="Tax equity bridge within the package",
        lenders=["BBVA", "CIBC", "Santander"],
        headline="Avantus secures $525 million for Aratina phase 2",
        tags=["phased", "storage"],
        tranches=[
            tranche("construction funding", "CONSTRUCTION_LOAN"),
            tranche("tax equity bridge", "TAX_EQUITY_BRIDGE"),
            tranche("letters of credit", "LETTER_OF_CREDIT"),
        ],
    )

    u = "https://mercomcapital.com/avantus-closes-1-billion-credit-facility-to-expand-project-portfolio/"
    add(
        "avantus-credit-facility-2026",
        "Avantus, corporate credit facility",
        "SOLAR",
        src=MERCOM,
        url=u,
        date="2026-08-04",
        sponsor="Avantus",
        quantum=1_000_000_000,
        headline="Avantus closes a $1 billion credit facility to expand its portfolio",
        tags=["corporate-facility"],
        tranches=[tranche("credit facility", "REVOLVER", amt(1_000_000_000, MERCOM, u, "2026-08-04"))],
    )

    u = "https://mercomcapital.com/origis-energy-secures-900-million-corporate-credit-facility/"
    add(
        "origis-credit-facility-2026",
        "Origis Energy, corporate credit facility",
        "SOLAR",
        src=MERCOM,
        url=u,
        date="2026-06-22",
        sponsor="Origis Energy",
        quantum=900_000_000,
        headline="Origis Energy secures a $900 million corporate credit facility",
        tags=["corporate-facility"],
        tranches=[tranche("credit facility", "REVOLVER", amt(900_000_000, MERCOM, u, "2026-06-22"))],
    )

    u = "https://mercomcapital.com/project-finance-brief-masdar-closes-financing-solar-storage-project/"
    add(
        "masdar-rtc-2026",
        "Masdar, round-the-clock solar and storage",
        "SOLAR_PLUS_STORAGE",
        src=MERCOM,
        url=u,
        date="2026-07-15",
        sponsor="Masdar",
        quantum=5_100_000_000,
        close="2026-07",
        location="Abu Dhabi, United Arab Emirates",
        capacity="5.2 GW solar with 19 GWh battery storage",
        headline="Masdar closes $5.1 billion for a round-the-clock solar and storage project",
        summary="Non-US, included as a scale comparator for round-the-clock solar plus storage.",
        tags=["international", "round-the-clock", "mega-project"],
        tranches=[tranche("project financing", "CONSTRUCTION_TO_TERM", amt(5_100_000_000, MERCOM, u, "2026-07-15"))],
    )

    # -- storage ------------------------------------------------------------

    u = "https://mercomcapital.com/project-finance-brief-fidra-secures-312-million-for-energy-storage-project/"
    add(
        "fidra-storage-2026",
        "Fidra, energy storage project financing",
        "STORAGE",
        src=MERCOM,
        url=u,
        date="2026-07-22",
        sponsor="Fidra",
        quantum=312_000_000,
        headline="Fidra secures $312 million for an energy storage project",
        tags=["storage"],
        tranches=[tranche("project financing", "CONSTRUCTION_TO_TERM", amt(312_000_000, MERCOM, u, "2026-07-22"))],
    )

    u = "https://www.ess-news.com/2026/03/25/1-billion-in-texas-project-financing-esvolta-and-doral-renewables-secure-funds-for-ercot-solar-storage/"
    add(
        "esvolta-boxcar-2026",
        "esVolta, Boxcar battery storage",
        "STORAGE",
        src="ess-news",
        url=u,
        date="2026-03-25",
        sponsor="esVolta",
        quantum=139_600_000,
        close="2026-03",
        location="Texas",
        capacity="150 MW / 300 MWh",
        lenders=["MUFG"],
        headline="esVolta secures $139.6 million for the Boxcar storage project",
        tags=["ercot", "storage", "two-hour"],
        tranches=[tranche("project financing", "CONSTRUCTION_TO_TERM", amt(139_600_000, "ess-news", u, "2026-03-25"))],
    )

    # -- wind ---------------------------------------------------------------

    u = "https://www.energy-storage.news/apex-finances-670mw-of-energy-storage-wind-with-us2-79-billion-financial-commitments/"
    add(
        "apex-2026",
        "Apex Clean Energy, wind and storage commitments",
        "WIND",
        src=ESN,
        url=u,
        date="2026-01-15",
        sponsor="Apex Clean Energy",
        quantum=2_790_000_000,
        capacity="670 MW of energy storage and wind",
        headline="Apex finances 670 MW of storage and wind with $2.79 billion of commitments",
        tags=["wind", "storage", "portfolio"],
        tranches=[tranche("financial commitments", "CONSTRUCTION_TO_TERM", amt(2_790_000_000, ESN, u, "2026-01-15"))],
    )

    # -- data centres --------------------------------------------------------

    u = "https://www.datacenterdynamics.com/en/news/dc-blox-secures-115bn-green-loan-for-atlanta-data-center-development/"
    add(
        "dc-blox-green-loan-2026",
        "DC Blox, Douglas County green loan",
        "DATA_CENTRE",
        src=DCD,
        url=u,
        date=None,
        sponsor="DC Blox",
        quantum=1_150_000_000,
        close="2026-05",
        location="Douglas County, Georgia",
        headline="DC Blox secures a $1.15 billion green loan",
        lenders=[
            "ING Capital (structuring and administrative agent)",
            "Mizuho Bank",
            "Natixis CIB",
        ],
        tags=["green-loan", "data-centre"],
        tranches=[tranche("green loan", "CONSTRUCTION_TO_TERM", amt(1_150_000_000, DCD, u, None))],
    )

    u = "https://www.datacenterdynamics.com/en/news/rowan-digital-infrastructure-secures-12bn-financing-to-fund-data-center-build-out/"
    add(
        "rowan-digital-2026",
        "Rowan Digital Infrastructure, build-out financing",
        "DATA_CENTRE",
        src=DCD,
        url=u,
        date=None,
        sponsor="Rowan Digital Infrastructure",
        quantum=1_200_000_000,
        lenders=["SMBC", "MUFG", "Mizuho", "Societe Generale"],
        headline="Rowan Digital Infrastructure secures $1.2 billion",
        summary="First financing issued under Rowan's green finance framework.",
        tags=["green-loan", "data-centre"],
        tranches=[tranche("financing", "CONSTRUCTION_TO_TERM", amt(1_200_000_000, DCD, u, None))],
    )

    u = "https://www.datacenterdynamics.com/en/news/edgecore-raises-19-billion-in-green-financing/"
    add(
        "edgecore-2026",
        "EdgeCore, green financing",
        "DATA_CENTRE",
        src=DCD,
        url=u,
        date=None,
        sponsor="EdgeCore Digital Infrastructure",
        quantum=1_900_000_000,
        close="2026-05",
        lenders=["MUFG", "TD Securities", "ING Capital", "Scotiabank", "Santander"],
        headline="EdgeCore raises $1.9 billion in green financing",
        tags=["green-loan", "data-centre"],
        tranches=[tranche("green financing", "CONSTRUCTION_TO_TERM", amt(1_900_000_000, DCD, u, None))],
    )

    u = "https://www.datacenterdynamics.com/en/news/apac-data-center-firm-airtrunk-secures-23bn-in-funding-for-jhb2-campus-in-johor-bahru-malaysia/"
    add(
        "airtrunk-jhb2-2026",
        "AirTrunk, JHB2 campus",
        "DATA_CENTRE",
        src=DCD,
        url=u,
        date=None,
        sponsor="AirTrunk",
        quantum=2_300_000_000,
        location="Johor Bahru, Malaysia",
        headline="AirTrunk secures $2.3 billion for the JHB2 campus",
        summary="Non-US, included as an APAC hyperscale comparator.",
        tags=["international", "data-centre"],
        tranches=[tranche("funding", "CONSTRUCTION_TO_TERM", amt(2_300_000_000, DCD, u, None))],
    )

    u = "https://www.datacenterdynamics.com/en/news/nscale-closes-900m-revolving-credit-facility/"
    add(
        "nscale-rcf-2026",
        "Nscale, revolving credit facility",
        "DATA_CENTRE",
        src=DCD,
        url=u,
        date=None,
        sponsor="Nscale",
        quantum=900_000_000,
        headline="Nscale closes a $900 million revolving credit facility",
        tags=["revolver", "data-centre"],
        tranches=[tranche("revolving credit facility", "REVOLVER", amt(900_000_000, DCD, u, None))],
    )

    u = "https://www.datacenterdynamics.com/en/news/digital-edge-secures-575m-financing-for-apac-data-centers/"
    add(
        "digital-edge-2026",
        "Digital Edge, APAC financing",
        "DATA_CENTRE",
        src=DCD,
        url=u,
        date=None,
        sponsor="Digital Edge",
        quantum=575_000_000,
        location="Asia-Pacific",
        headline="Digital Edge secures $575 million for APAC data centres",
        summary="Non-US, included as an APAC comparator.",
        tags=["international", "data-centre"],
        tranches=[tranche("financing", "CONSTRUCTION_TO_TERM", amt(575_000_000, DCD, u, None))],
    )

    u = "https://www.datacenterdynamics.com/en/news/singtel-secures-4759-million-green-loan-for-singapore-data-center/"
    add(
        "singtel-green-loan-2026",
        "Singtel, Singapore green loan",
        "DATA_CENTRE",
        src=DCD,
        url=u,
        date=None,
        sponsor="Singtel",
        quantum=475_900_000,
        location="Singapore",
        headline="Singtel secures a $475.9 million green loan",
        summary="Non-US, included as an APAC green-loan comparator.",
        tags=["international", "green-loan"],
        tranches=[tranche("green loan", "CONSTRUCTION_TO_TERM", amt(475_900_000, DCD, u, None))],
    )

    u = "https://www.datacenterdynamics.com/en/news/aligned-extends-sustainability-linked-loan-by-more-than-1-billion/"
    add(
        "aligned-sll-2026",
        "Aligned Data Centers, sustainability-linked loan extension",
        "DATA_CENTRE",
        src=DCD,
        url=u,
        date=None,
        sponsor="Aligned Data Centers",
        quantum=1_000_000_000,
        headline="Aligned extends its sustainability-linked loan by more than $1 billion",
        tags=["sustainability-linked", "data-centre"],
        tranches=[tranche("sustainability-linked loan", "REVOLVER", amt(1_000_000_000, DCD, u, None, note="Reported as more than $1 billion of extension."))],
    )

    u = "https://www.datacenterdynamics.com/en/news/dc-blox-adds-600m-to-existing-debt-facility/"
    add(
        "dc-blox-upsize-2026",
        "DC Blox, debt facility upsize",
        "DATA_CENTRE",
        src=DCD,
        url=u,
        date=None,
        sponsor="DC Blox",
        quantum=600_000_000,
        headline="DC Blox adds around $600 million to an existing debt facility",
        tags=["upsize", "data-centre"],
        tranches=[tranche("facility upsize", "CONSTRUCTION_TO_TERM", amt(600_000_000, DCD, u, None))],
    )

    u = "https://www.ifre.com/ifr-awards/2327933/financing-package-blue-owl-capitalbeignet-investors-us27.3bn-23.6-year-bond"
    add(
        "meta-hyperion-beignet-2025",
        "Meta and Blue Owl, Hyperion campus (Beignet Investor LLC)",
        "DATA_CENTRE",
        src=IFR,
        url=u,
        date="2025-10-16",
        sponsor="Blue Owl Capital (80%) and Meta (20%), through Beignet Investor LLC",
        quantum=27_294_000_000,
        close="2025-10-16",
        location="Richland Parish, Louisiana",
        contract="HYPERSCALE_LEASE",
        offtake=S(
            "Meta lease commitments support the notes; S&P rated them A+, one notch below Meta's long-term rating",
            IFR,
            u,
            "2025-10-16",
        ),
        headline="Blue Owl and Beignet Investor price a $27.294 billion 23.6-year bond",
        summary="A bankruptcy-remote SPV issuing a single 144A-for-life senior secured fully amortising bond, priced at par with a 6.581% fixed coupon and an expected final maturity of 30 May 2049.",
        tags=["securitisation", "144a", "hyperscale", "spv"],
        lenders=["Morgan Stanley (sole bookrunner)", "PIMCO", "BlackRock"],
        tranches=[
            tranche(
                "senior secured notes",
                "NOTES",
                amt(27_294_000_000, IFR, u, "2025-10-16"),
                pricing=S(6.581, IFR, u, "2025-10-16", unit="% fixed coupon", note="Priced at par, quarterly pay, 30/360."),
                tenor=S(23.6, IFR, u, "2025-10-16", unit="years", note="Expected final maturity 30 May 2049."),
            )
        ],
    )

    # -- AI compute ----------------------------------------------------------

    u = "https://www.sec.gov/Archives/edgar/data/1769628/000176962826000129/ex991.htm"
    add(
        "coreweave-ddtl4-2026",
        "CoreWeave, DDTL 4.0 facility",
        "AI_COMPUTE",
        src=SEC,
        url=u,
        date="2026-03-31",
        sponsor="CoreWeave",
        quantum=8_500_000_000,
        close="2026-03-31",
        contract="EQUIPMENT_LEASE",
        offtake=S(
            "Secured by high-performance computing infrastructure and an associated customer contract",
            SEC,
            u,
            "2026-03-31",
        ),
        headline="CoreWeave closes an $8.5 billion delayed draw term loan facility",
        summary="Rated A3 by Moody's and A (low) by DBRS. Initial borrowing capacity around $7.5 billion, rising to $8.5 billion as the underlying assets stabilise.",
        tags=["gpu-backed", "investment-grade", "delayed-draw"],
        tranches=[
            tranche(
                "floating rate tranche",
                "TERM_LOAN",
                pricing=S(225.0, SEC, u, "2026-03-31", unit="bps over SOFR"),
                tenor=S(6.0, SEC, u, "2026-03-31", unit="years", note="Matures March 2032."),
            ),
            tranche(
                "fixed rate tranche",
                "TERM_LOAN",
                pricing=S(5.9, SEC, u, "2026-03-31", unit="% fixed", note="Reported as approximately 5.9%."),
                tenor=S(6.0, SEC, u, "2026-03-31", unit="years", note="Matures March 2032."),
            ),
        ],
    )

    u = "https://investors.coreweave.com/news/news-details/2026/CoreWeave-Closes-3-1-Billion-Loan-Facility-Expanding-Access-to-Public-Markets-for-GPU-Backed-Financing/default.aspx"
    add(
        "coreweave-3-1bn-2026",
        "CoreWeave, $3.1 billion loan facility",
        "AI_COMPUTE",
        src="CoreWeave investor relations",
        url=u,
        date="2026-05-18",
        sponsor="CoreWeave",
        quantum=3_100_000_000,
        contract="EQUIPMENT_LEASE",
        headline="CoreWeave closes a $3.1 billion loan facility",
        tags=["gpu-backed"],
        tranches=[tranche("loan facility", "TERM_LOAN", amt(3_100_000_000, "CoreWeave investor relations", u, "2026-05-18"))],
    )

    u = (
        "https://www.globenewswire.com/news-release/2026/06/09/3308896/0/en/"
        "apollo-leads-35-billion-capital-solution-for-broadcom-ai-xpv-platform-"
        "in-partnership-with-blackstone-and-leading-global-banks.html"
    )
    src = "Apollo Global Management, press release"
    # The release names the A1 and A2 tranches but states no sizes, coupons,
    # spreads, ratings or guarantee terms. The figures widely quoted in the
    # press trace to Bloomberg reporting, which is not readable from a free
    # source, so they are recorded here as undisclosed rather than restated.
    NOT_IN_RELEASE = (
        "The release names the A1 and A2 tranches but does not state sizes, "
        "coupons, spreads, ratings or guarantee terms."
    )
    add(
        "broadcom-ai-xpv-2026",
        "Broadcom AI XPV Platform, Apollo-led capital solution",
        "AI_COMPUTE",
        src=src,
        url=u,
        date="2026-06-09",
        sponsor="Apollo-managed funds, with Blackstone and global banks",
        quantum=35_000_000_000,
        close="2026-06-09",
        contract="EQUIPMENT_LEASE",
        offtake=S(
            "Supports Anthropic's expansion of more than 1 GW of compute for training and inference, starting mid-2026",
            src, u, "2026-06-09",
        ),
        capacity="Platform designed to enable over 20 GW of compute capacity through 2028",
        credit=ND(NOT_IN_RELEASE),
        headline="Apollo leads a $35 billion capital solution for the Broadcom AI XPV Platform",
        summary="Committed capital across a multi-year draw schedule, structured in A1 and A2 tranches. Tranche economics and credit support are not disclosed in the release.",
        tags=["ai-compute", "equipment-lease", "platform", "private-credit"],
        lenders=["Apollo (Atlas SP Partners)", "Blackstone", "Global banks"],
        tranches=[
            tranche("Class A1", "NOTES", ND(NOT_IN_RELEASE), ND(NOT_IN_RELEASE), ND(NOT_IN_RELEASE)),
            tranche("Class A2", "NOTES", ND(NOT_IN_RELEASE), ND(NOT_IN_RELEASE), ND(NOT_IN_RELEASE)),
        ],
    )

    # -- wind ---------------------------------------------------------------

    RN = "Renewables Now"
    WPE = "Windpower Engineering & Development"

    u = "https://renewablesnow.com/news/exus-lands-usd-356m-in-construction-financing-for-wind-repowerings-1298334/"
    add(
        "exus-repowering-2026",
        "Exus Renewables North America, wind repowerings",
        "WIND",
        src=RN, url=u, date="2026-07-20",
        sponsor="Exus Renewables North America",
        quantum=356_000_000,
        location="Pennsylvania",
        capacity="Two wind repowering projects",
        headline="Exus lands about $356 million in construction financing for wind repowerings",
        tags=["repowering", "wind"],
        tranches=[tranche("construction financing", "CONSTRUCTION_LOAN", amt(356_000_000, RN, u, "2026-07-20"))],
    )

    u = "https://renewablesnow.com/news/vineyard-wind-1-closes-usd-1-2bn-tax-equity-financing-837782/"
    add(
        "vineyard-wind-1-te",
        "Vineyard Wind 1, tax equity",
        "WIND",
        src=RN, url=u, date="2023-10-26",
        sponsor="Vineyard Wind",
        quantum=1_200_000_000,
        location="Offshore Massachusetts",
        credit="Tax equity financing",
        headline="Vineyard Wind 1 closes $1.2 billion tax equity financing",
        summary="Offshore wind, included as the tax-equity scale comparator for the sector.",
        tags=["offshore", "tax-equity"],
        tranches=[tranche("tax equity", "TAX_EQUITY", amt(1_200_000_000, RN, u, "2023-10-26"))],
    )

    u = "https://renewablesnow.com/news/rwe-closes-tax-equity-financing-for-220-mw-wind-farm-in-texas-725695/"
    add(
        "rwe-texas-wind-te",
        "RWE, 220 MW Texas wind tax equity",
        "WIND",
        src=RN, url=u, date="2020-12-23",
        sponsor="RWE",
        location="Texas",
        capacity="220 MW",
        credit="Tax equity financing",
        headline="RWE closes tax equity financing for a 220 MW Texas wind farm",
        tags=["ercot", "tax-equity"],
        tranches=[tranche("tax equity", "TAX_EQUITY")],
    )

    u = "https://renewablesnow.com/news/eon-closes-tax-equity-financing-for-201-mw-wind-farm-in-texas-640422/"
    add(
        "eon-texas-wind-te",
        "E.ON, 201 MW Texas wind tax equity",
        "WIND",
        src=RN, url=u, date="2019-01-24",
        sponsor="E.ON",
        location="Texas",
        capacity="201 MW",
        credit="Tax equity financing",
        headline="E.ON closes tax equity financing for a 201 MW Texas wind farm",
        tags=["ercot", "tax-equity"],
        tranches=[tranche("tax equity", "TAX_EQUITY")],
    )

    u = "https://www.windpowerengineering.com/business-news-projects/quinbrook-closes-financing-200-mw-wind-project-oklahoma/"
    add(
        "quinbrook-oklahoma-wind",
        "Quinbrook, 200 MW Oklahoma wind",
        "WIND",
        src=WPE, url=u, date="2018-01-16",
        sponsor="Quinbrook Infrastructure Partners",
        location="Oklahoma",
        capacity="200 MW",
        headline="Quinbrook closes financing for a 200 MW Oklahoma wind project",
        tags=["spp", "wind"],
        tranches=[tranche("project financing", "CONSTRUCTION_TO_TERM")],
    )

    u = "https://www.windpowerengineering.com/innergex-closes-financing-for-texas-foard-city-wind-project/"
    add(
        "innergex-foard-city",
        "Innergex, Foard City wind",
        "WIND",
        src=WPE, url=u, date="2019-05-10",
        sponsor="Innergex Renewable Energy",
        location="Texas",
        headline="Innergex closes financing for the Foard City wind project",
        tags=["ercot", "wind"],
        tranches=[tranche("project financing", "CONSTRUCTION_TO_TERM")],
    )

    u = "https://renewablesnow.com/news/unicredit-credit-agricole-to-fund-134-mw-wind-repowering-in-italy-1296096/"
    add(
        "italy-repowering-2026",
        "134 MW Italian wind repowering",
        "WIND",
        src=RN, url=u, date="2026-06-09",
        sponsor="Not named in the source recorded for this entry",
        quantum=215_800_000,
        location="Italy",
        capacity="134 MW repowering",
        lenders=["UniCredit", "Credit Agricole"],
        headline="UniCredit and Credit Agricole to fund a 134 MW Italian wind repowering",
        summary="Non-US, included as a European repowering comparator. Debt reported as over EUR 187 million.",
        tags=["international", "repowering"],
        tranches=[tranche("debt financing", "TERM_LOAN", amt(215_800_000, RN, u, "2026-06-09", note="Reported as over EUR 187 million."))],
    )

    u = "https://renewablesnow.com/news/nwb-bank-ekf-join-lenders-of-322-mw-dutch-repowering-wind-project-708726/"
    add(
        "dutch-repowering-322mw",
        "322 MW Dutch wind repowering",
        "WIND",
        src=RN, url=u, date="2020-08-04",
        sponsor="Not named in the source recorded for this entry",
        location="Netherlands",
        capacity="322 MW repowering",
        lenders=["NWB Bank", "EKF"],
        headline="NWB Bank and EKF join lenders of a 322 MW Dutch repowering project",
        summary="Non-US, included as a European repowering comparator.",
        tags=["international", "repowering"],
        tranches=[tranche("debt financing", "TERM_LOAN")],
    )

    u = "https://mercomcapital.com/project-finance-brief-engie-financing-wind-solar-projects/"
    add(
        "engie-wind-solar-2022",
        "ENGIE, wind and solar financing",
        "WIND",
        src=MERCOM, url=u, date="2022-04-04",
        sponsor="ENGIE",
        quantum=800_000_000,
        headline="ENGIE raises $800 million in financing for wind and solar projects",
        tags=["portfolio", "wind", "solar"],
        tranches=[tranche("financing", "CONSTRUCTION_TO_TERM", amt(800_000_000, MERCOM, u, "2022-04-04"))],
    )

    # -- storage -------------------------------------------------------------

    ESSN = "ess-news"
    u = "https://www.ess-news.com/2026/05/22/bess-financing-spearmint-closes-450-million-for-600-mwh-ercot-project-powerbank-leases-60-mwh-across-new-york/"
    add(
        "spearmint-2026",
        "Spearmint Energy, 600 MWh ERCOT storage",
        "STORAGE",
        src=ESSN, url=u, date="2026-05-22",
        sponsor="Spearmint Energy",
        quantum=450_000_000,
        close="2026-05",
        location="Texas",
        capacity="600 MWh",
        headline="Spearmint closes $450 million for a 600 MWh ERCOT project",
        tags=["ercot", "storage"],
        tranches=[tranche("project financing", "CONSTRUCTION_TO_TERM", amt(450_000_000, ESSN, u, "2026-05-22"))],
    )

    u = "https://www.energy-storage.news/esvolta-closes-us450-million-expanded-credit-facility-to-expand-us-bess-portfolio/"
    add(
        "esvolta-facility-2026",
        "esVolta, expanded credit facility",
        "STORAGE",
        src=ESN, url=u, date="2026-06-08",
        sponsor="esVolta",
        quantum=450_000_000,
        location="United States",
        headline="esVolta closes a $450 million expanded credit facility",
        tags=["corporate-facility", "storage"],
        tranches=[tranche("credit facility", "REVOLVER", amt(450_000_000, ESN, u, "2026-06-08"))],
    )

    u = "https://www.energy-storage.news/broad-reach-power-secures-financing-for-880mw-of-ercot-and-caiso-projects/"
    add(
        "broad-reach-880mw",
        "Broad Reach Power, ERCOT and CAISO portfolio",
        "STORAGE",
        src=ESN, url=u, date="2023-07-31",
        sponsor="Broad Reach Power",
        location="ERCOT and CAISO",
        capacity="880 MW",
        headline="Broad Reach Power secures financing for 880 MW of ERCOT and CAISO projects",
        tags=["ercot", "caiso", "portfolio"],
        tranches=[tranche("project financing", "CONSTRUCTION_TO_TERM")],
    )

    u = "https://mercomcapital.com/project-finance-brief-energy-vault-battery-storage-project/"
    add(
        "energy-vault-150mw",
        "Energy Vault, 150 MW battery storage",
        "STORAGE",
        src=MERCOM, url=u, date="2025-10-29",
        sponsor="Energy Vault",
        capacity="150 MW",
        headline="Energy Vault acquires a 150 MW battery storage project",
        tags=["storage", "acquisition"],
        tranches=[tranche("project financing", "CONSTRUCTION_TO_TERM")],
    )

    # -- other technologies ---------------------------------------------------

    u = "https://mercomcapital.com/project-finance-brief-atlas-renewable-secures-3-billion-refinancing/"
    add(
        "atlas-renewable-refi",
        "Atlas Renewable Energy, portfolio refinancing",
        "SOLAR",
        src=MERCOM, url=u, date="2026-02-25",
        sponsor="Atlas Renewable Energy",
        quantum=3_000_000_000,
        headline="Atlas Renewable secures a $3 billion refinancing",
        tags=["refinancing", "portfolio"],
        tranches=[tranche("refinancing", "TERM_LOAN", amt(3_000_000_000, MERCOM, u, "2026-02-25"))],
    )

    u = "https://www.sec.gov/Archives/edgar/data/0001368265/000110465926057158/clne-20260507xex99d1.htm"
    add(
        "clean-energy-fuels-rng-2026",
        "Clean Energy Fuels and bp, East Valley dairy RNG",
        "RNG",
        src=SEC, url=u, date="2026-05-07",
        sponsor="Clean Energy Fuels, joint venture with bp",
        cod="Placed in service Q1 2026",
        location="Idaho",
        capacity="Approximately 3.5 million gallons of RNG annually",
        headline="Clean Energy Fuels places the East Valley dairy RNG project in service",
        tags=["rng", "joint-venture"],
        tranches=[tranche("project financing", "CONSTRUCTION_TO_TERM")],
    )

    u = "https://www.solsystems.com/news/sol-systems-secures-675-million-in-revolving-construction-financing-to-power-its-clean-energy-pipeline/"
    src = "Sol Systems, press release"
    add(
        "sol-systems-warehouse-2025",
        "Sol Systems, revolving construction warehouse",
        "SOLAR_PLUS_STORAGE",
        src=src, url=u, date="2025-07-16",
        sponsor="Sol Systems",
        quantum=675_000_000,
        cod="First group of projects expected online by end 2026",
        location="Illinois, Ohio and Texas",
        capacity="Initial 500 MW of solar and storage",
        credit="Facility funds construction loans, tax equity bridge loans and letters of credit",
        headline="Sol Systems secures $675 million in revolving construction financing",
        summary="A construction warehouse facility rather than a single-project financing: one revolving line funding a pipeline, arranged by KKR Capital Markets.",
        tags=["warehouse", "revolver", "portfolio"],
        lenders=[
            "BBVA New York Branch", "ING Capital", "Intesa Sanpaolo New York Branch",
            "National Australia Bank", "NatWest", "Natixis New York Branch",
            "KKR Capital Markets (arranger)",
        ],
        tranches=[
            tranche("revolving construction warehouse", "REVOLVER", amt(675_000_000, src, u, "2025-07-16")),
        ],
    )

    u = "https://biomassmagazine.com/articles/20330/project-financing-agreement-to-support-3-rng-facilities"
    src = "Biomass Magazine"
    add(
        "pine-creek-rng",
        "Pine Creek Renewables, RNG portfolio",
        "RNG",
        src=src, url=u, date=None,
        sponsor="Pine Creek Renewables",
        capacity="Three RNG facilities",
        credit="Senior secured credit facility",
        headline="Fiera Infrastructure Private Debt closes a senior secured facility for three RNG facilities",
        tags=["rng", "private-debt"],
        lenders=["Fiera Infrastructure Private Debt"],
        tranches=[tranche("senior secured credit facility", "TERM_LOAN")],
    )

    u = "https://www.sec.gov/Archives/edgar/data/1368265/000110465923125562/tm2332773d1_ex99-1.htm"
    add(
        "clean-energy-stonepeak",
        "Clean Energy Fuels, Stonepeak senior secured term loan",
        "RNG",
        src=SEC, url=u, date="2023-12-01",
        sponsor="Clean Energy Fuels",
        quantum=300_000_000,
        credit="Proceeds fund new RNG production facilities and fuelling infrastructure",
        headline="Clean Energy Fuels enters a $300 million senior secured term loan with Stonepeak",
        summary="Includes an additional $100 million delayed draw commitment.",
        tags=["rng", "term-loan", "delayed-draw"],
        lenders=["Stonepeak"],
        tranches=[
            tranche("senior secured term loan", "TERM_LOAN", amt(300_000_000, SEC, u, "2023-12-01")),
            tranche("delayed draw commitment", "TERM_LOAN", amt(100_000_000, SEC, u, "2023-12-01")),
        ],
    )

    u = "https://investor.atmeta.com/investor-news/press-release-details/2025/Meta-Announces-Joint-Venture-with-Funds-Managed-by-Blue-Owl-Capital-to-Develop-Hyperion-Data-Center/default.aspx"
    src = "Meta, press release"
    add(
        "meta-blue-owl-jv-2025",
        "Meta and Blue Owl, Hyperion joint venture",
        "DATA_CENTRE",
        src=src, url=u, date=None,
        sponsor="Meta and funds managed by Blue Owl Capital",
        location="Richland Parish, Louisiana",
        contract="HYPERSCALE_LEASE",
        headline="Meta announces a joint venture with Blue Owl Capital to develop the Hyperion data centre",
        summary="The equity layer beneath the Beignet Investor bond: Blue Owl funds hold 80% of the joint venture and Meta retains 20%.",
        tags=["joint-venture", "hyperscale", "equity-layer"],
        tranches=[tranche("joint venture equity", "SPONSOR_EQUITY")],
    )

    return {
        "_note": "Extracted fields only, each with the source it came from. Article bodies are never stored.",
        "deals": deals,
    }


if __name__ == "__main__":
    payload = build()
    OUT.write_text(json.dumps(payload, indent=2) + "\n", encoding="utf-8")
    print(f"wrote {len(payload['deals'])} records to {OUT.relative_to(OUT.parents[2])}")
