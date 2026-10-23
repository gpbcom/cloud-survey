# Computing & Digital-Infrastructure Leaders, 1964–October 2026: Company Dossier on Market Share, Valuation, Margins/Capex, Regulation and Adoption Criteria

Across the 83 company units I could assess, profitability was decisive most often (44 units, 53%), followed by compatibility (27, 33%) and relative advantage (22, 27%). Regulation usually changed the timing and price of a company's rise or fall, but rarely its direction: four of the largest antitrust interventions (US v. IBM, US v. Microsoft, EU v. Intel, US v. Google search) left the targeted firm's market share largely intact.

## TL;DR
- **Criteria, counted company by company:** profitability decisive in 44 of 83 units, compatibility 27, relative advantage 22, portability 4, reliability 3, complexity 1, security 1, observability 0. The ranking matches the earlier 24-case report; most calls are my interpretive judgements and are labelled as such.
- **Current state (22 Oct 2026):** AWS 28%, Microsoft 20%, Google 15% of a $143.4bn Q2-2026 cloud-infrastructure market (Synergy, revenue); AWS and Microsoft each 30–40% in the UK (CMA, 2024); TSMC 72.5% of foundry revenue (TrendForce, 2Q26); Intel's x86 unit share 69.3%, lowest since 1995 (Mercury, Q2 2026); Google about 86–92% of search in the US, UK and large EU markets but about 28% in Russia and 47% in South Korea (StatCounter, 2026); Nvidia the most valuable company at about $5.5tn; OpenAI ($852bn) and Anthropic ($965bn) valued privately.
- **Regulation:** fines were repeatedly cut (Intel: €1.06bn → €376m → €237m) and structural remedies rejected (Chrome divestiture denied, 2 Sept 2025). Only IBM's 1969 unbundling and market-access/export-control rules (China, Russia, US chip controls) clearly reshaped market structure. The 2025–26 cloud rules (CMA, EU DMA, Data Act, DORA) have not yet shifted shares measurably.

## Key Findings

1. **Profitability is the most common decisive criterion, but mostly as the mechanism of decline.** Falls show up as profit collapse (the BUNCH, GE and RCA exits, Wang, DEC, Commodore, Sun, SGI, AOL, Rackspace, the HP/Verizon clouds). Rises are driven more by relative advantage (System/360, VAX, PageRank, iPhone, CUDA, EC2) or compatibility (IBM PC clones, Windows, x86, Android).
2. **Compatibility is most often decisive at turning points:** System/360, Compaq's IBM-compatible PC, the Windows "applications barrier" (US v. Microsoft), Itanium vs. AMD64, OS/2, Windows Phone, CUDA, and the Microsoft-licensing advantage the UK CMA found benefits Azure.\[1\]
3. **Data is very uneven by era.** No country-level share data exists for mainframes, minicomputers or time-sharing before 1990 (N/A in the spreadsheet). Country-level series exist only for search, browsers and mobile OS (StatCounter, monthly since 2009), cloud (regulator studies) and PCs (IDC/Gartner, regional).
4. **Analysts disagree mainly on definitions.** For 2025, IDC put Lenovo at 24.9% of 284.7m PCs and Gartner at 27.2% of over 270m.\[2\]\[3\] Mercury reports AMD at 30.7% (PC + server), 34.1% (incl. IoT/semi-custom) and 46.4% (Xeon SP vs. EPYC only).\[4\]\[5\] All are kept with definitions; none is silently chosen.

## 1. Methodology

**Scope.** All companies in the 1964–2026 chronology, grouped by era. Firms with identical stories are grouped into one unit (e.g. Tymshare/GEIS/Comshare; AltaVista/Excite/Lycos; Rackspace/HP Helion/Verizon cloud): 84 units, 83 assessable (Gaia-X is an association with no market share).

**Source labels:** [P] primary filing/regulator/court; [A] academic or business history; [I] industry analyst; [J] journalistic; [B] blog/aggregator; [K] figure from the task brief or the established literature, not re-fetched in this session — verify against the primary document before publication.

**Segment definitions:**
- Cloud (Synergy): worldwide cloud infrastructure services revenue (IaaS + PaaS + hosted private cloud). UK CMA: share of UK supply by value, in ranges, 2024.
- Foundry: TrendForce = top-10 foundry revenue; Counterpoint = "pure-foundry" revenue (different denominator).
- x86 (Mercury): unit shipments unless marked revenue. Client = desktop + mobile; overall = PC + server.
- PCs: IDC and Gartner unit shipments, with different PC definitions.
- Smartphones (Gartner 2007–09): unit sales to end users.
- Search/browsers (StatCounter): share of page views referred, from a web-traffic panel; not query counts and biased against in-app use, which is why Korea's Internet Trend puts Naver near 63.8% versus StatCounter's ~44%.\[6\]\[7\]
- Mainframes 1960s–80s: share of US "EDP industry" or "general-purpose computer" revenue as defined in US v. IBM.
- Valuation: market cap for listed firms on a stated date; announced (and closing) deal value for acquisitions; post-money round valuations for private firms.

**Limits.** Full year-end market-cap series 1964–2026 need CRSP/Compustat, which I could not access; those cells are N/A with a pointer.

## 2. Company dossiers

### 2.1 Mainframe era

**IBM**
- *Profile:* System/360 announced 1964; peak relative dominance in the 1960s–70s; loss in 1992; rebuilt around services and software; sold PCs (2005) and x86 servers (2014); today hybrid cloud and mainframes.
- *Share:* US EDP industry 52% (1961), 50% (1968), 37% (1972), about 37% (1982); mainframe sales 69.4% (1981) → 73.8% (1983) — Fisher, McKie & Mancke (1983) via *Regulation* (Cato, 1985) [A via J].\[8\] CMU lecture notes [A/B]: a "sustained 70% share" in the 1960s, about 50% of the global market by 1976, 25% by 1985.\[9\] The popular "70% worldwide / 80% US" figure [B] reflects market definition: IBM measured itself at about 40%, the US government at about 70% (Stanford CS181) [B].\[10\]\[11\]\[12\] Country shares before 1990: N/A.
- *Financials:* revenue $1.8bn (1960), $7.2bn (1970);\[9\]\[13\] loss of about $5bn in 1992 (CMU, citing annual reports) [B]\[9\] — check against the 10-K.
- *Criteria:* compatibility decisive [A, documented: S/360 designed as a compatible family with emulation, SPREAD task group 1961];\[13\] profitability decisive [Int]; relative advantage and reliability contributing.
- *Regulation:* US v. IBM filed 17 Jan 1969, trial from 19 May 1975, dropped "without merit" 8 Jan 1982 [J];\[14\] unbundling announced 23 June 1969, when IBM separately priced systems engineering, maintenance, education, custom programming and seventeen software products (IEEE Engineering and Technology History Wiki; WSJ, 24 Jun 1969); EU undertaking 1984 [K]; DORA critical provider 18 Nov 2025 [P].\[15\] The case did not break IBM up (Cato argues it raised prices and slowed IBM);\[8\] unbundling mattered more because it created the software market.

**The BUNCH (Burroughs, UNIVAC/Sperry → Unisys 1986, NCR, Control Data, Honeywell); GE (exit 1970), RCA (exit 1971)**
- *Share:* IDC estimated in 1984 that the BUNCH would take less than $2bn of an $11.4bn mainframe market, IBM most of the rest (NYT, 5 Feb 1984) [I via J].\[16\] Individual shares: N/A (Fisher-McKie-Mancke and US v. IBM exhibits are the right sources).
- *Valuation:* N/A (pre-EDGAR). Unisys formed 1986 [K]; NCR to AT&T 1991 [K]; CDC break-up 1992 [K].
- *Criteria:* profitability decisive for all [Int]; compatibility decisive for Burroughs and Sperry (non-IBM architectures), contributing for the others; CDC's rise was relative-advantage driven (6600 supercomputer) [K].
- *Regulation:* CDC's private suit against IBM settled in 1973, CDC acquiring IBM's Service Bureau Corporation [K].

**Amdahl:** compatibility decisive (IBM-compatible hardware) [Int]; relative advantage and profitability contributing; fully owned by Fujitsu from 1997 [K].

### 2.2 Time-sharing: Tymshare, GE Information Services, Comshare
Rose in the late 1960s–70s selling interactive computing by the hour; displaced by minis and PCs. Tymshare went to McDonnell Douglas in 1984 [K]. Shares and valuations: N/A. Relative advantage decisive in the rise [K, Campbell-Kelly & Garcia-Swartz]; profitability decisive in the fall [Int]; complexity contributing.

### 2.3 Software
- **Informatics, ADR:** created by the 1969 unbundling [K, Campbell-Kelly 2003]. Profitability decisive; compatibility contributing. Data N/A.
- **Lotus:** relative advantage decisive (1-2-3 on the IBM PC) [K]; compatibility decisive in the fall (late to Windows) [Int]. IBM tender completed 5 Jul 1995: about $3.5bn equity value (IBM Q2-1995 10-Q) or about $3.2bn (Q3-1995 10-Q) [P] — both kept.\[17\]\[18\]
- **WordPerfect:** compatibility decisive (late on Windows) [Int]. Novell deal announced March 1994 at about $1.4bn in stock, worth about $855m at close in June 1994 (Deseret News) [J]; sold to Corel in 1996 for about $186–200m [J].\[19\]\[20\]
- **Ashton-Tate:** reliability decisive (buggy dBase IV, 1988) [K, Campbell-Kelly; Int]. Borland stock deal of about $440m, agreed 9 Jul 1991 (DOJ Competitive Impact Statement) [P].\[21\]
- **VisiCorp / Software Arts:** profitability decisive (royalty dispute) [K]; compatibility contributing.
- **Microsoft:** compatibility decisive [P: US v. Microsoft Findings of Fact, Nov 1999, "applications barrier to entry"]; profitability decisive; relative advantage and portability contributing. Market cap $3.974tn on 9 Oct 2026 [B].\[22\] Regulation: US v. Microsoft 1998–2001; EU €497m (2004) [K] and €561m (6 Mar 2013) for breaching its 2009 browser-choice commitment, after Windows 7 SP1 shipped without the choice screen from May 2011 to July 2012 so that "15 million users were never made aware that they could choose" (Reuters); CMA licensing finding 31 Jul 2025 [P];\[1\]\[23\] EU DMA preliminary view on Azure 25 Jun 2026 [J].\[24\]
- **Oracle:** portability decisive (database on every platform) [Int]; compatibility and profitability contributing. Bought Sun for $7.4bn ($9.50/share), completed 26–27 Jan 2010 (eWeek); FY2010 10-K: about $7.3bn, about $5.6bn net of cash and debt [P].\[25\]\[26\]\[27\] DORA critical provider [P].\[15\]
- **SAP:** relative advantage decisive (integrated ERP) [Int]; compatibility and complexity contributing. DORA critical provider [P].

### 2.4 Minicomputers
- **DEC:** peak of more than 120,000 employees and over $14bn revenue in 1990, No. 2 behind IBM (Britannica) [A];\[28\] MIT Sloan Review says about 130,000 [A];\[29\] one blog puts peak revenue at $14.6bn in FY1996 while loss-making [B]\[30\] (conflict flagged). Compaq deal announced 26 Jan 1998 at $9.6bn ($4.8bn cash + 150m shares; DEC 8-K) [P], closed June 1998;\[31\]\[32\]\[33\] a 2002 HP filing says $9.4bn [P];\[34\] 1997 revenue $13.1bn [J].\[35\] Relative advantage decisive in the rise, profitability in the fall; compatibility contributing.
- **Data General, Prime:** profitability decisive [Int]. Data General to EMC 1999 [K].
- **Wang:** peak of nearly $3bn revenue and about 32,000 employees in the late 1980s; Chapter 11 on 18 Aug 1992, emerged after 13 months (Washington Post; UPI) [J].\[36\]\[37\]\[38\] Compatibility and profitability decisive [Int].
- **HP:** survived by diversifying; portability, compatibility and profitability contributing, none decisive.

### 2.5 PCs and CPUs
- **PC shares 2025:** IDC — Lenovo 70.8m (24.9%), HP 57.5m (20.2%), Dell 41.1m (14.4%), Apple 25.6m (9.0%), total 284.7m (+8.1%) [I via J].\[2\] Gartner — Lenovo 73.6m (27.2%), Dell 41.4m (15.3%), Apple 24.8m (9.2%), total over 270m (+9.1%) [I].\[3\] IBM held about 26% of PCs worldwide in 1984 (Dataquest, via a 1985 transcript) [B, weak].\[39\]
- **Apple:** relative advantage and profitability decisive; compatibility, complexity, observability contributing [Int]. Market cap $4.918tn (9 Oct 2026) [B].\[22\] EU DMA gatekeeper 2023; DMA fines 2025 [K].
- **Commodore:** bankruptcy 29 Apr 1994 (some sources: 19 Apr), liquidated; Escom bought the assets in 1995 for about $14m [B].\[40\]\[41\]\[42\] Profitability decisive.
- **Tandy:** compatibility decisive (non-IBM-compatible TRS-80) [Int].
- **IBM PC:** compatibility and profitability decisive. Sold to Lenovo for $1.25bn ($650m cash + $600m stock; announced Dec 2004, closed May 2005; about $1.75bn including $500m of assumed liabilities) [J: China Daily; Forbes].\[43\]\[44\]\[45\]
- **Compaq:** compatibility and profitability decisive. Acquired by HP for about $25bn in stock, completed 3 May 2002 [P, HP 424B5].\[46\]\[47\]
- **Dell, Lenovo, Acer:** profitability decisive (cost models) [Int].
- **Intel:** relative advantage and compatibility decisive [Int]. Mercury Q2 2026: 69.3% of x86 PC + server units, down 6.5 points year on year; 65.9% including IoT/semi-custom [I via J].\[5\] EU: €1.06bn (2009), partly annulled 2022, re-imposed at €376,358,000 (2023), cut to €237,105,540 by the General Court on 10 Dec 2025 (T-1129/23) [P, CJEU];\[48\]\[49\] Intel's further appeal published April 2026 [J, MLex].\[50\] CHIPS Act subsidies [K].
- **AMD:** relative advantage and compatibility decisive [Int]. Mercury Q2 2026: client 30.3% (first time above 30%), overall 30.7%, server 34.5% (46.4% Xeon SP vs. EPYC), desktop 34.9%;\[4\]\[5\]\[51\]\[52\] Q1 2026: 38.1% of x86 revenue and 46.2% of server revenue; client share 24.1% in Q1 2025 [I via J].\[53\] Market cap $992bn (9 Oct 2026) [B].\[22\]

### 2.6 Networking
Novell: compatibility decisive (Windows NT bundled networking); complexity and profitability contributing. Cisco: compatibility decisive (multiprotocol, then TCP/IP); relative advantage contributing. IBM SNA: compatibility decisive (proprietary, displaced by TCP/IP). All [Int]; shares N/A.

### 2.7 Workstations and Unix
- **Sun:** profitability decisive (dot-com crash plus Linux on x86) [Int]; portability and compatibility contributing. Exit: Oracle, $7.4bn.\[26\]
- **SGI:** profitability decisive; bankruptcy 2009 [K].
- **Apollo:** compatibility decisive (proprietary vs. open systems); acquired by HP 1989 [K].
- **Red Hat:** portability and profitability decisive (Linux subscriptions) [Int]; security and reliability contributing. Acquired by IBM 2019 [K].

### 2.8 Browser war
- **Netscape:** relative advantage decisive; profitability decisive because Microsoft gave Internet Explorer away bundled with Windows [P, Findings of Fact]. Sold to AOL for $4.2bn in stock, announced 24 Nov 1998 [P, AOL 8-K].\[54\]
- **Internet Explorer:** compatibility decisive (Windows bundling) [P]; security contributing to the later decline [Int].
- **Firefox:** relative advantage, security, portability contributing. **Chrome:** relative advantage decisive; portability, observability, compatibility (defaults) contributing. Browser share series: N/A (StatCounter not retrieved this session).

### 2.9 Web navigation and search
- **AOL:** complexity and profitability decisive [Int]; observability contributing.
- **Yahoo:** profitability decisive; relative advantage contributing. Sold to Verizon for about $4.48bn, cut by $350m from $4.83bn on 20 Feb 2017 after its data breaches, completed 13 Jun 2017 [P, Verizon 10-Q]\[55\]\[56\] — the clearest case of security failure hitting valuation, though not the cause of the fall.
- **AltaVista, Excite, Lycos:** relative advantage decisive in the rise, profitability in the fall.
- **Google:** relative advantage and profitability decisive; compatibility contributing (paid defaults, found in *US v. Google*, 2024) [P]. StatCounter: worldwide 89.9%, US 85.2% (Sep 2026); Europe 89.65%, Asia 93.37% (Aug 2026); UK 91.75%, Germany 88.49%, France 88.76%, Canada 85.66%, Brazil 87.50%, India 97.45% (Apr 2026), Czechia 79.08%, South Korea 46.49%, Russia 27.83%, China about 1.4–2.1% [I via B].\[57\]\[58\]\[59\]\[60\] IPO at $85 on 18 Aug 2004, about $23bn valuation, $1.67bn raised [P; J].\[61\]\[62\]\[63\] Alphabet $4.301tn (9 Oct 2026) [B].\[22\]
- **Baidu, Yandex, Naver, Seznam:** relative advantage decisive (local language) [Int], with market access exogenous (Google's 2010 exit from mainland China; Russia) [K]. Aug 2026: Yandex 70.32% (Russia), Baidu 59.10% (China), Naver 43.80% (Korea), Seznam 15.79% (Czechia) [I via B].\[58\] China data is low-reliability: the same panel shows Yandex at 11.4%, and Baidu swung 44.6–64.0% between Jan 2025 and Aug 2026.\[6\]\[58\] Internet Trend puts Naver at about 63.8% (Mar 2026); conflict flagged.\[6\]
- **Bing:** about 5.3% worldwide, 8.9% US;\[6\]\[57\] compatibility (defaults) contributing.

### 2.10 Mobile
- **Gartner (sales to end users):** Nokia smartphones 49.4% (2007), 43.7% (2008). By OS 2009 (2008): Symbian 46.9% (52.4%), RIM 19.9%, iPhone 14.4%, Android 3.9%, WebOS 0.7%; 172m units. Nokia all handsets 38.6% (2008), 36.4% (2009) [I via J].\[64\]\[65\]\[66\]
- **Nokia:** compatibility decisive (fragmented Symbian, then Windows Phone) [Int]; relative advantage, complexity, profitability contributing. Devices sold to Microsoft for €5.44bn (€3.79bn business + €1.65bn patents), closed 25 Apr 2014 [P].\[67\]\[68\]\[69\]
- **RIM/BlackBerry:** security decisive in its rise (secure enterprise email) [Int]; relative advantage and compatibility contributing.
- **Palm:** relative advantage and profitability decisive; sold to HP for about $1.2bn ($5.70/share), announced 28 Apr 2010 [P].\[70\]
- **Windows Mobile/Phone:** compatibility decisive (app gap); observability contributing.
- **Android:** portability and compatibility decisive; profitability contributing. EU 2018 €4.343bn, cut to €4.125bn by the General Court on 14 Sep 2022 (Case T-604/18), "a reduction of less than 5%" (Hausfeld); India CCI 2022; KFTC [K].
- **Samsung** (portability, profitability contributing), **Motorola** (profitability decisive), **Huawei/Xiaomi** (Huawei's fall outside China driven by 2019 US sanctions — regulatory, outside the eight criteria) [K]. Kantar country shares: N/A (not retrieved).

### 2.11 Semiconductors
- **Foundry (TrendForce, 2Q26):** TSMC 72.5% (~$40.2bn; 1Q26 72.3%), Samsung 5.9% ($3.26bn; 1Q26 6.5%), SMIC 5.4% (1Q26 5.1%), UMC 3.9%, GlobalFoundries 3.2% (~$1.79bn); top-10 $53.49bn [I].\[71\]\[72\] 4Q24: TSMC 67.1%, Samsung 8.1% [I via J].\[73\] Counterpoint pure-foundry: TSMC 73% [I].\[74\]
- **TSMC:** relative advantage and reliability decisive (dependable yields vs. Samsung) [Int]; profitability contributing. Market cap about $2.45tn (Oct 2026) [B].\[75\]
- **Samsung Foundry:** reliability decisive (leading-edge yields) [Int]. **GlobalFoundries:** profitability decisive (quit 7nm, 2018) [K]. **SMIC:** regulation-driven — gaining share without access to EUV tools [J].\[76\]
- **Nvidia:** compatibility (CUDA), relative advantage and profitability decisive [Int]. Market cap $5.536tn (9 Oct 2026) or about $5.65tn (5 Oct) [B];\[22\]\[77\] first company past $4tn and $5tn (2025) [J].\[78\] China SAMR preliminary finding of 15 Sep 2025 that Nvidia breached the Anti-Monopoly Law and its 2020 Mellanox conditions, with fines of 1–10% of prior-year sales possible [P, Nvidia 10-Q; J];\[79\]\[80\]\[81\] US export controls [P];\[79\] China about 13% (~$17bn) of FY2025 revenue [J].\[82\]
- **Arm:** portability and relative advantage decisive [Int]. IPO at $51 on 14 Sep 2023: about $54.5bn fully diluted (StoneX) or $52.3bn at pricing, about $65bn at first close (Fortune) [J].\[83\]\[84\]
- **Apple silicon:** relative advantage decisive; compatibility (Rosetta) contributing. **Qualcomm:** compatibility and profitability decisive; KFTC, EU and FTC cases [K].

### 2.12 Cloud
- **Worldwide (Synergy, revenue):** Q2 2026 AWS 28%, Microsoft 20%, Google 15% (record) of $143.4bn (release of 30 Jul 2026, via trade press) [I via J/B];\[85\]\[86\] Q1 2026 28/21/14 of $128.6bn;\[87\] Q2 2025 30/20/13;\[88\] Q2 2022 AWS 34%, Azure 21%, Google 10%, Alibaba 5%, IBM 4%, Salesforce 3%, Tencent 3%, Oracle 2% of $55bn [I via J].\[89\] One outlier (16idc.com: 31/24/12) contradicts all other reports and is rejected.\[90\] Canalys put AWS at 32% in Q2 2025 vs. Synergy's 30%.\[91\]
- **UK:** AWS and Microsoft each 30–40% by value in 2024; Google 5–10%; Oracle and IBM under 5% each; UK spend £10.5bn;\[92\] Microsoft's share up and AWS's down since 2020 [P, CMA final decision summary, 31 Jul 2025].\[1\]\[93\]
- **France, Netherlands, Japan:** Autorité de la concurrence (2023), ACM (2022), JFTC (2022) studies not retrieved: N/A.
- **AWS:** relative advantage and profitability decisive; compatibility and reliability contributing. Q2 2026 sales $42.23bn (+37%) [P via B].\[85\] Amazon $2.830tn (9 Oct 2026) [B].\[22\]
- **Azure:** compatibility decisive [P, CMA: Microsoft licensing advantages its own cloud];\[1\]\[23\] profitability contributing; about 43% growth in Q2 2026 [P via B].\[94\]
- **Google Cloud:** profitability decisive (turning profitable funded its gains) [Int]; relative advantage (AI/TPUs) contributing. H1 2026 revenue $44.8bn vs. $43.2bn in all of 2024 [P via B].\[87\]
- **Alibaba, Tencent, Huawei Cloud:** shares driven by China's protected market; no criterion decisive.
- **IBM Cloud:** profitability decisive (under-investment); bought Verizon's cloud 2017 [K]. **Oracle Cloud:** relative advantage and compatibility contributing. **Salesforce:** relative advantage decisive [K].
- **OVHcloud, T-Systems, Scaleway, IONOS:** profitability decisive (cannot match hyperscaler capex) [Int]; security contributing as legal sovereignty vs. the US CLOUD Act (SecNumCloud, SREN law) [K]; OVHcloud reliability contributing (2021 Strasbourg fire) [K]. Deutsche Telekom and Orange are DORA critical providers [P].\[15\]
- **VMware (Broadcom):** compatibility and profitability decisive [Int]. Acquired for about $61bn plus about $8bn net debt (~$69bn); announced 26 May 2022, completed 22 Nov 2023 [P; J].\[95\]\[96\]\[97\]\[98\]\[99\] CISPE asked the General Court on 24 Jul 2025 to annul the 12 Jul 2023 clearance (T-503/25); the Commission published its reasons only on 13 May 2025, 672 days later; CISPE complained to the Ombudsman in Dec 2025 and alleges price rises of more than ten times [P/J].\[95\]\[100\]\[101\]\[102\] No remedy as of 22 Oct 2026.
- **Rackspace, HP Helion, Verizon cloud, Dell:** profitability decisive (scale and capex) [K].

### 2.13 AI era
- **OpenAI** (post-money): $300bn (Mar 2025); $852bn (31 Mar 2026, $122bn round incl. Amazon up to ~$50bn, Nvidia $30bn, SoftBank $30bn); employee buyback at $852bn (Aug 2026).\[103\]\[104\] October 2026: Reuters reports talks on about $30bn at a pre-money valuation of $1.4tn or more — **not closed** [J].\[105\] Relative advantage decisive; profitability not established (annualised revenue about $50bn at end-September 2026).\[105\]
- **Anthropic:** Series G $30bn at $380bn (Feb 2026); Series H $65bn at $965bn (28 May 2026) [J/B].\[106\] IPO expected mid-November 2026 at a discussed $1.5–2tn — *a projection* [J, Reuters via Quartz].\[105\]\[107\] Annualised revenue about $65bn in July 2026; OpenAI disputes Anthropic's gross booking of cloud-marketplace sales.\[105\]\[107\] Relative advantage decisive; security (safety positioning) and reliability contributing.
- **CoreWeave:** IPO at $40 on 27 Mar 2025 (below $47–55), $1.5bn raised, about $19bn basic or $23bn diluted [P/J].\[108\]\[109\]\[110\] Q2 2026: revenue $2.575bn (+112%); adjusted operating income $128m (5%) vs. $200m (16%) a year earlier; GAAP operating loss −$49m (−1.9%); net interest $640m; net loss $626m; backlog $104.2bn; capex $9.4bn.\[111\]\[112\]\[113\]\[114\]\[115\] FY2026 guidance: revenue $12.4–13.2bn, adjusted operating income $0.96–1.15bn, capex $35–39bn.\[116\] FY2025 capex $14.9bn; year-end backlog $66.8bn [P via J/B].\[117\] Relative advantage and profitability contributing; interest burden is the key risk.
- **Nebius, Crusoe, Lambda:** data not retrieved: N/A.
- **Hyperscaler capex:** 2025 actuals Alphabet $91.4bn, Meta $72.2bn [P via B];\[118\] big four about $410bn (Fortune) [J].\[119\] 2026 guidance rose through the year: Feb — Amazon ~$200bn, Alphabet $175–185bn, Meta $115–135bn;\[118\]\[120\] 29 Apr — Microsoft ~$190bn (calendar 2026), Alphabet $180–190bn, Meta $125–145bn;\[119\] late Jul — Alphabet $195–205bn, Meta $130–145bn, Amazon ~$220bn; combined about $720–745bn [B; definitions differ].\[121\] Quarterly Q1/Q2 2026: Microsoft $31.9bn/$41.0bn (incl. finance leases), Alphabet $35.7bn/$44.9bn, Amazon $44.2bn/$54.2bn, Meta $19.84bn/$31.08bn [P via B].\[119\] Visible Alpha consensus (CNBC, 28 Jul 2026): Amazon $207.4bn, Microsoft $190.1bn [J].\[122\]

### 2.14 Failed and stalled contrast cases
Itanium: compatibility decisive (lost to AMD64). OS/2: compatibility decisive (applications barrier) [P; Int], profitability contributing. Cloudwatt and Numergy: profitability decisive (state-backed sovereign clouds that never reached scale) [K]; shares N/A. Gaia-X: association, not assessable.

## 3. Did regulation change outcomes?

| Intervention | Date / outcome | Effect on shares | Effect on valuation / timing | Verdict |
|---|---|---|---|---|
| IBM unbundling | Announced 23 Jun 1969 (IEEE ETHW; WSJ, 24 Jun 1969) | Created the independent software market | Enabled entrants | **Structural, decisive** |
| US v. IBM | 1969–1982, dropped [J] | IBM EDP share 50% → 37% (1968–72), then flat [A] | Slowed IBM (Cato 1985) | Timing only |
| AT&T decrees 1956, 1982–84 | [K] | Cheap Unix licences seeded workstations | — | Structural, indirect |
| US v. Microsoft; EU 2004, 2013 | €497m [K]; €561m (6 Mar 2013, browser-choice breach; Reuters) | IE stayed dominant for years; fell to Firefox/Chrome | None lasting | No direction change |
| EU v. Intel | €1.06bn → annulled in part → €376m → €237m (10 Dec 2025) [P]\[48\]\[49\] | AMD's recovery was product-led (Mercury) | Negligible | No direction change |
| EU Google Shopping / Android | Shopping €2,424,495,000, upheld by the Court of Justice 10 Sep 2024 (C-48/22 P); Android €4.343bn cut to €4.125bn by the General Court 14 Sep 2022 (T-604/18) | EU search share still ~89–92% [I] | None visible | No direction change |
| US v. Google search | Liability Aug 2024; remedies 2 Sep 2025: no Chrome/Android divestiture, exclusive deals banned, data sharing; appeals 2026 [P; J]\[123\]\[124\] | US share ~85–86% | Alphabet shares rose as much as 9.2% intraday to $230.86 after the ruling (Bloomberg Law, 3 Sep 2025) | Removed downside |
| China/Russia market access | 2010 Google exit [K] | Baidu, Yandex lead at home [I] | National split | **Structural, decisive** |
| US chip export controls; SAMR v. Nvidia | 2022–26; 15 Sep 2025 [P] | SMIC grows without EUV | China ~13% of Nvidia revenue\[82\] | **Decisive in China** |
| UK CMA cloud | 31 Jul 2025 decision; Mar 2026 egress/interoperability commitments;\[125\] SMS probe of Microsoft business software from May 2026 (Civo, secondary) [P/B] | No reversal yet | — | Pending |
| EU DMA cloud | Opened 18 Nov 2025; preliminary gatekeeper view 25 Jun 2026; final reportedly Nov 2026 [P/J]\[24\]\[126\] | Not designated yet | — | Pending |
| EU Data Act | Egress reduced 12 Sep 2025, abolished 12 Jan 2027 [K] | Too early | — | Pending |
| DORA | 19 critical providers, 18 Nov 2025 [P]\[127\] | None yet | Compliance cost | Neutral |
| SREN / SecNumCloud | [K] | Helps qualified local firms in public procurement | — | Marginal |
| Broadcom–VMware | Cleared 12 Jul 2023; T-503/25 pending [P]\[95\]\[128\] | Customer migration (CISPE claim) | — | Pending |

**Conclusion:** in 62 years, fines and conduct remedies never reversed a dominant computing firm's position. Structural interventions on market definition and access did: unbundling, the AT&T decrees, national market closure, export controls. Product discontinuities unseated more incumbents than any case above. The 2025–27 cloud rules are the first ex-ante attempt to lower switching costs — the compatibility criterion itself — and should be judged on Synergy and CMA shares in 2027–28.

## 4. Criteria synthesis

| Criterion | Decisive (n = 83) | Share | Previous report (n = 24) | Main documented basis |
|---|---|---|---|---|
| Profitability | 44 | 53% | 12 | Bankruptcies (Wang, Commodore, SGI), deal prices, filings |
| Compatibility | 27 | 33% | 9 | Microsoft Findings of Fact; CMA 2025; S/360 histories |
| Relative advantage | 22 | 27% | 9 | Business histories; Mercury, TrendForce share shifts |
| Portability | 4 | 5% | 3 | Oracle, Red Hat, Android, Arm (interpretive) |
| Reliability | 3 | 4% | 0 | Ashton-Tate; TSMC vs. Samsung yields (interpretive) |
| Complexity | 1 | 1% | 3 | AOL (interpretive) |
| Security | 1 | 1% | 0 | RIM (interpretive) |
| Observability | 0 | 0% | 2 | Contributing only |

Profitability is decisive so often partly because profit collapse is how every fall becomes visible — it is often a symptom. The more explanatory pair is relative advantage (rises) and compatibility (lock-in and turning points). Security and reliability decide outcomes only in B2B infrastructure. Roughly 70% of decisive calls are my interpretive judgements; only the IBM, Microsoft, Azure and Netscape calls rest directly on a court or regulator finding. Treat the counts as ordinal: the ranking is robust, the exact numbers are not.

## 5. Recommendations
1. Check the definitions column before comparing numbers; most contradictions (IDC vs. Gartner; Mercury's three AMD shares; StatCounter vs. Internet Trend) are definitional.
2. Fill N/A cells in this order: (a) CRSP year-end market caps 1964–2026 for IBM, DEC, Burroughs/Unisys, Wang, Apple, Microsoft, Intel; (b) StatCounter browser and mobile-OS series by country; (c) Kantar iOS/Android by country; (d) Autorité de la concurrence, ACM and JFTC cloud shares; (e) 10-K segment margins (AWS since 2015, Intelligent Cloud, Google Cloud since 2020).
3. Verify every [K] item against the primary document, especially the EU Microsoft, Google and Qualcomm fines and the Data Act dates.
4. Re-run the cloud analysis after the DMA designation (expected Nov 2026) and the Anthropic IPO, which will bring an S-1 with audited margins.

## 6. Caveats
- The search budget ran out before browser, Kantar, French/Dutch/Japanese cloud and long-run market-cap series could be retrieved; these are N/A, not estimated.
- Synergy 2026 shares come from trade-press reports of Synergy's releases.
- Market caps for 22 Oct 2026 were not captured; the latest are 5–14 Oct 2026 aggregator values [B] that differ by up to about 5%.
- Forward-looking items are labelled: 2026 capex guidance, Anthropic IPO valuation, OpenAI's $1.4tn round, DMA timing.
- No separate bibliography: each figure's source is named in the text and in the spreadsheet's source column.

## Appendix: Spreadsheet (Deliverable A) — one tab per block

**Tab 1: Market share, worldwide**
```
company,segment,metric,geo,period,value,unit,source,type,notes
IBM,EDP industry,revenue share,US,1961,52,%,Fisher-McKie-Mancke via Cato 1985,A,
IBM,EDP industry,revenue share,US,1968,50,%,same,A,
IBM,EDP industry,revenue share,US,1972,37,%,same,A,
IBM,EDP industry,revenue share,US,1982,37,%,same,A,approx
IBM,mainframes,sales share,US,1981,69.4,%,same,A,
IBM,mainframes,sales share,US,1983,73.8,%,same,A,
IBM,computers,share,World,1976,50,%,CMU slides,B,
IBM,computers,share,World,1985,25,%,CMU slides,B,
BUNCH combined,mainframes,revenue,World,1984,<2.0 of 11.4,$bn,IDC via NYT,I/J,
BUNCH individual,mainframes,share,any,1964-86,N/A,,,,no source
IBM PC,PCs,share,World,1984,26,%,Dataquest via transcript,B,weak
Lenovo,PCs,units,World,2025,24.9,%,IDC,I,70.8m
HP Inc,PCs,units,World,2025,20.2,%,IDC,I,57.5m
Dell,PCs,units,World,2025,14.4,%,IDC,I,41.1m
Apple,PCs,units,World,2025,9.0,%,IDC,I,2024 8.7%
Lenovo,PCs,units,World,2025,27.2,%,Gartner,I,73.6m
Dell,PCs,units,World,2025,15.3,%,Gartner,I,
Apple,PCs,units,World,2025,9.2,%,Gartner,I,
Intel,x86 PC+server,units,World,Q2 2026,69.3,%,Mercury,I,
AMD,x86 PC+server,units,World,Q2 2026,30.7,%,Mercury,I,
AMD,x86 incl IoT,units,World,Q2 2026,34.1,%,Mercury,I,
AMD,x86 client,units,World,Q1 2025,24.1,%,Mercury,I,
AMD,x86 client,units,World,Q1 2026,29.6,%,Mercury,I,
AMD,x86 client,units,World,Q2 2026,30.3,%,Mercury,I,
AMD,x86 server,units,World,Q2 2026,34.5,%,Mercury,I,46.4 Xeon SP vs EPYC
AMD,x86 desktop,units,World,Q2 2026,34.9,%,Mercury,I,
AMD,x86 total,revenue,World,Q1 2026,38.1,%,Mercury,I,
AMD,x86 server,revenue,World,Q1 2026,46.2,%,Mercury,I,
Nokia,smartphones,sales,World,2007,49.4,%,Gartner,I,
Nokia,smartphones,sales,World,2008,43.7,%,Gartner,I,
Symbian,smartphone OS,sales,World,2008,52.4,%,Gartner,I,
Symbian,smartphone OS,sales,World,2009,46.9,%,Gartner,I,
RIM,smartphone OS,sales,World,2009,19.9,%,Gartner,I,
iOS,smartphone OS,sales,World,2009,14.4,%,Gartner,I,
Android,smartphone OS,sales,World,2009,3.9,%,Gartner,I,
WebOS,smartphone OS,sales,World,2009,0.7,%,Gartner,I,
Nokia,all handsets,sales,World,2008,38.6,%,Gartner,I,
Nokia,all handsets,sales,World,2009,36.4,%,Gartner,I,
TSMC,foundry,revenue,World,4Q24,67.1,%,TrendForce,I,
Samsung Foundry,foundry,revenue,World,4Q24,8.1,%,TrendForce,I,
TSMC,foundry,revenue,World,1Q26,72.3,%,TrendForce,I,
TSMC,foundry,revenue,World,2Q26,72.5,%,TrendForce,I,$40.2bn
Samsung Foundry,foundry,revenue,World,1Q26,6.5,%,TrendForce,I,
Samsung Foundry,foundry,revenue,World,2Q26,5.9,%,TrendForce,I,
SMIC,foundry,revenue,World,1Q26,5.1,%,TrendForce,I,
SMIC,foundry,revenue,World,2Q26,5.4,%,TrendForce,I,
UMC,foundry,revenue,World,2Q26,3.9,%,TrendForce,I,
GlobalFoundries,foundry,revenue,World,2Q26,3.2,%,TrendForce,I,
TSMC,pure foundry,revenue,World,Q2 2026,73,%,Counterpoint,I,other denominator
AWS,cloud infra,revenue,World,Q2 2022,34,%,Synergy,I,market $55bn
Azure,cloud infra,revenue,World,Q2 2022,21,%,Synergy,I,
Google Cloud,cloud infra,revenue,World,Q2 2022,10,%,Synergy,I,
Alibaba,cloud infra,revenue,World,Q2 2022,5,%,Synergy,I,
IBM,cloud infra,revenue,World,Q2 2022,4,%,Synergy,I,
Salesforce,cloud infra,revenue,World,Q2 2022,3,%,Synergy,I,
Tencent,cloud infra,revenue,World,Q2 2022,3,%,Synergy,I,
Oracle,cloud infra,revenue,World,Q2 2022,2,%,Synergy,I,
AWS,cloud infra,revenue,World,Q2 2025,30,%,Synergy,I,Canalys 32
Azure,cloud infra,revenue,World,Q2 2025,20,%,Synergy,I,
Google Cloud,cloud infra,revenue,World,Q2 2025,13,%,Synergy,I,
AWS,cloud infra,revenue,World,Q1 2026,28,%,Synergy,I,$128.6bn
Azure,cloud infra,revenue,World,Q1 2026,21,%,Synergy,I,
Google Cloud,cloud infra,revenue,World,Q1 2026,14,%,Synergy,I,
AWS,cloud infra,revenue,World,Q2 2026,28,%,Synergy,I,$143.4bn
Azure,cloud infra,revenue,World,Q2 2026,20,%,Synergy,I,
Google Cloud,cloud infra,revenue,World,Q2 2026,15,%,Synergy,I,
Google,search,referrals,World,Sep 2026,89.9,%,StatCounter,I/B,
Bing,search,referrals,World,Sep 2026,5.3,%,StatCounter,I/B,
Browsers,browser,page views,World,2009-26,N/A,,StatCounter,,to fill
```

**Tab 2: Market share by country**
```
company,segment,metric,geo,period,value,unit,source,type,notes
AWS,cloud infra,supply by value,UK,2024,30-40,%,CMA 31 Jul 2025,P,down since 2020
Microsoft,cloud infra,supply by value,UK,2024,30-40,%,CMA,P,up since 2020
Google,cloud infra,supply by value,UK,2024,5-10,%,CMA,P,
Oracle; IBM,cloud infra,supply by value,UK,2024,<5 each,%,CMA,P,
Cloud total,cloud,spend,UK,2024,10.5,GBP bn,CMA,P,
Cloud,cloud,share,FR/NL/JP,2022-23,N/A,,AdlC/ACM/JFTC,,to fill
Google,search,referrals,US,Sep 2026,85.2,%,StatCounter,I/B,
Google,search,referrals,UK,2026,91.75,%,StatCounter,I/B,
Google,search,referrals,Germany,2026,88.49,%,StatCounter,I/B,
Google,search,referrals,France,2026,88.76,%,StatCounter,I/B,
Google,search,referrals,Canada,2026,85.66,%,StatCounter,I/B,
Google,search,referrals,Brazil,2026,87.50,%,StatCounter,I/B,
Google,search,referrals,Europe,Aug 2026,89.65,%,StatCounter,I/B,
Google,search,referrals,Asia,Aug 2026,93.37,%,StatCounter,I/B,
Google,search,referrals,India,Apr 2026,97.45,%,StatCounter,I/B,
Google,search,referrals,Japan,2026,55.4-66.4,%,StatCounter,B,conflict
Google,search,referrals,Czechia,Aug 2026,79.08,%,StatCounter,I/B,
Seznam,search,referrals,Czechia,Aug 2026,15.79,%,StatCounter,I/B,
Google,search,referrals,South Korea,Aug 2026,46.49,%,StatCounter,I/B,
Naver,search,referrals,South Korea,Aug 2026,43.80,%,StatCounter,I/B,Internet Trend ~63.8
Yandex,search,referrals,Russia,Aug 2026,70.32,%,StatCounter,I/B,
Google,search,referrals,Russia,Aug 2026,27.83,%,StatCounter,I/B,
Baidu,search,referrals,China,Aug 2026,59.10,%,StatCounter,I/B,low reliability
Google,search,referrals,China,Apr 2026,1.85,%,StatCounter,I/B,
Smartphone OS,mobile,sales,all countries,2010-26,N/A,,Kantar,,to fill
Mainframes/minis,all,share,any country,1964-90,N/A,,none exists,,
```

**Tab 3: Valuation**
```
company,event,metric,date,value,unit,source,type,notes
Nvidia,listed,market cap,2026-10-09,5536,$bn,finhacker.cz,B,~5650 on 5 Oct
Apple,listed,market cap,2026-10-09,4918,$bn,finhacker.cz,B,
Alphabet,listed,market cap,2026-10-09,4301,$bn,finhacker.cz,B,
Microsoft,listed,market cap,2026-10-09,3974,$bn,finhacker.cz,B,
Amazon,listed,market cap,2026-10-09,2830,$bn,finhacker.cz,B,
Meta,listed,market cap,2026-10-09,1831,$bn,finhacker.cz,B,
Broadcom,listed,market cap,2026-10-09,1726,$bn,finhacker.cz,B,
AMD,listed,market cap,2026-10-09,992,$bn,finhacker.cz,B,
TSMC,listed,market cap,2026-10,~2450,$bn,AlphaSense,B,
Google,IPO,valuation,2004-08-18,~23,$bn,prospectus/WaPo,P/J,
Arm,IPO,valuation,2023-09-14,52.3-54.5,$bn,Fortune/StoneX,J,
CoreWeave,IPO,valuation,2025-03-27,19-23,$bn,CoreWeave/CNBC,P/J,
DEC,to Compaq,deal,1998-01-26,9.6,$bn,DEC 8-K,P,9.4 per HP
Netscape,to AOL,deal,1998-11-24,4.2,$bn,AOL 8-K,P,
Lotus,to IBM,deal,1995-07-05,3.5 / 3.2,$bn,IBM 10-Qs,P,conflict
WordPerfect,to Novell,deal,1994-06,0.855,$bn,Deseret News,J,1.4 announced
WordPerfect,to Corel,deal,1996,0.186-0.2,$bn,Deseret News,J,
Ashton-Tate,to Borland,deal,1991-07-09,0.44,$bn,DOJ CIS,P,
Compaq,to HP,deal,2002-05-03,~25,$bn,HP 424B5,P,
IBM PC,to Lenovo,deal,2005-05,1.25,$bn,China Daily/Forbes,J,1.75 incl liabilities
Sun,to Oracle,deal,2010-01-27,7.4,$bn,eWeek/Oracle 10-K,J/P,7.3; 5.6 net
Palm,to HP,deal,2010-04-28,~1.2,$bn,HP/Palm release,P,
Nokia D&S,to Microsoft,deal,2014-04-25,5.44,EUR bn,Microsoft/Nokia,P,
Yahoo,to Verizon,deal,2017-06-13,4.48,$bn,Verizon 10-Q,P,from 4.83
VMware,to Broadcom,deal,2023-11-22,~61 / ~69,$bn,VMware DEF 14A/DCD,P/J,
OpenAI,round,post-money,2025-03,300,$bn,RevenueMemo,B,
OpenAI,round,post-money,2026-03-31,852,$bn,Reuters,J,
OpenAI,proposed round,pre-money,2026-10,>=1400,$bn,Reuters,J,not closed
Anthropic,Series G,post-money,2026-02,380,$bn,Pinggy/ValueAddVC,B,
Anthropic,Series H,post-money,2026-05-28,965,$bn,same,B,
Anthropic,IPO expected,target,2026-11,1500-2000,$bn,Reuters,J,projection
All listed,year-end,market cap,1964-2026,N/A,,CRSP needed,,to fill
```

**Tab 4: Financials and margins**
```
company,metric,period,value,unit,source,type,notes
IBM,revenue,1960,1.8,$bn,CMU slides,B,
IBM,revenue,1970,7.2,$bn,CMU slides,B,
IBM,net loss,1992,~5,$bn,CMU slides,B,check 10-K
DEC,revenue,1990,>14,$bn,Britannica,A,
DEC,revenue,1997,13.1,$bn,Spokesman-Review,J,
Wang,revenue,1984,2.1,$bn,Lewiston Tribune,J,profit $210m
Wang,revenue,~1988,~3,$bn,UPI/WaPo,J,
CoreWeave,adj op margin,Q2 2025,16,%,CoreWeave,P,
CoreWeave,revenue,Q2 2026,2.575,$bn,CoreWeave,P,
CoreWeave,adj op margin,Q2 2026,5,%,CoreWeave,P,
CoreWeave,GAAP op margin,Q2 2026,-1.9,%,CoreWeave 10-Q,P,
CoreWeave,net loss,Q2 2026,-626,$m,CoreWeave,P,
CoreWeave,backlog,2026-06-30,104.2,$bn,CoreWeave,P,
CoreWeave,revenue guidance,FY2026,12.4-13.2,$bn,CoreWeave,P,projection
AWS,segment sales,Q2 2026,42.23,$bn,Amazon,P/B,
Google Cloud,revenue,FY2024,43.2,$bn,Alphabet,P/B,
Google Cloud,revenue,H1 2026,44.8,$bn,Alphabet,P/B,
Segment margins (AWS; Intelligent Cloud; Google Cloud; IBM; Intel; Nvidia; TSMC),op margin,annual,N/A,,10-K,,to fill
```

**Tab 5: Capex**
```
company,metric,period,value,unit,source,type,notes
Alphabet,capex,FY2025,91.4,$bn,Introl,B,
Meta,capex,FY2025,72.2,$bn,Introl,B,
Big four,capex,FY2025,~410,$bn,Fortune,J,
Microsoft,capex incl leases,Q1/Q2 2026,31.9/41.0,$bn,Analysis Atlas,B,
Alphabet,capex,Q1/Q2 2026,35.7/44.9,$bn,Analysis Atlas,B,
Amazon,capex,Q1/Q2 2026,44.2/54.2,$bn,Analysis Atlas,B,
Meta,capex,Q1/Q2 2026,19.84/31.08,$bn,Analysis Atlas,B,
Amazon,guidance,FY2026,~200 (Feb) / ~220 (Jul),$bn,Introl/YieldTheory,B,projection
Alphabet,guidance,FY2026,175-185 / 195-205,$bn,same,B,projection
Meta,guidance,FY2026,115-135 / 130-145,$bn,same,B,projection
Microsoft,guidance,CY2026,~190,$bn,Analysis Atlas,B,projection
Big four,guidance,FY2026,720-745,$bn,YieldTheory/FT,B/J,projection
CoreWeave,capex,FY2025,14.9,$bn,CoreWeave,P,
CoreWeave,capex,Q2 2026,9.4,$bn,CoreWeave,P,
CoreWeave,guidance,FY2026,35-39,$bn,CoreWeave,P,projection
Hyperscalers,capex,FY2015-2024,N/A,,10-K,,to fill
```

**Tab 6: Regulatory timeline** — the Section 3 table plus these dated events: 1969-01-17 US v. IBM filed (dropped 1982-01-08) [J];\[14\] 1991-10-17 DOJ complaint on Borland/Ashton-Tate [P];\[21\] 2022-01-26 General Court partial annulment of Intel fine [P];\[49\] 2023-09-22 Intel fine re-adopted at €376.358m [P];\[129\] 2025-01-28 CMA provisional findings [J];\[130\] 2025-07-24 CISPE action T-503/25 [P];\[101\] 2025-07-31 CMA final decision [P];\[23\]\[131\] 2025-09-02 Google remedies [P];\[132\] 2025-09-15 SAMR preliminary finding on Nvidia [P];\[80\] 2025-11-18 DMA cloud investigations and DORA designations [P];\[133\]\[134\] 2025-12-10 Intel fine cut to €237.106m [P];\[135\] 2026-01-16 Google notice of appeal [B];\[123\] 2026-04 Intel appeal published [J];\[50\] 2026-06-25 DMA preliminary gatekeeper view on AWS/Azure [J].\[24\]

**Tab 7: Criteria matrix** (D decisive, C contributing, N none; Doc = rests on a court/regulator/history finding, Int = my interpretation, K = literature not re-verified)
```
unit,rel_adv,port,profit,complex,observ,secur,reliab,compat,basis
IBM,C,N,D,N,N,N,C,D,Doc/Int
Burroughs,N,N,D,N,N,N,N,D,Int
Sperry-Unisys,N,N,D,N,N,N,N,D,Int
NCR,N,N,D,N,N,N,N,C,Int
Control Data,D,N,D,N,N,N,N,C,K
Honeywell,N,N,D,N,N,N,N,C,Int
GE computers,N,N,D,N,N,N,N,C,K
RCA computers,N,N,D,N,N,N,N,C,K
Amdahl,C,N,C,N,N,N,N,D,Int
Tymshare/GEIS/Comshare,D,N,D,C,N,N,N,N,K
Informatics/ADR,N,N,D,N,N,N,N,C,K
Lotus,D,N,C,N,N,N,N,D,Int
WordPerfect,C,N,N,N,N,N,N,D,Int
Ashton-Tate,N,N,N,N,N,N,D,C,K
VisiCorp/Software Arts,N,N,D,N,N,N,N,C,K
Microsoft,C,C,D,N,N,N,N,D,Doc
Oracle,N,D,C,N,N,N,N,C,Int
SAP,D,N,N,C,N,N,N,C,Int
DEC,D,N,D,N,N,N,N,C,Doc/Int
Data General,C,N,D,N,N,N,N,N,Int
Wang,N,N,D,N,N,N,N,D,Doc/Int
Prime,N,N,D,N,N,N,N,C,Int
HP,N,C,C,N,N,N,N,C,Int
Apple,D,N,D,C,C,N,N,C,Int
Commodore,N,N,D,N,N,N,N,C,Doc/Int
Tandy,N,N,C,N,N,N,N,D,Int
IBM PC,N,N,D,N,N,N,N,D,Int
Compaq,N,N,D,N,N,N,N,D,Int
Dell,C,N,D,N,N,N,N,N,Int
Lenovo,N,N,D,N,N,N,N,C,Int
Acer,N,N,D,N,N,N,N,N,Int
Intel,D,N,C,N,N,N,N,D,Doc/Int
AMD,D,N,N,N,N,N,N,D,Doc/Int
Novell,N,N,C,C,N,N,N,D,Int
Cisco,C,N,N,N,N,N,N,D,Int
IBM SNA,N,N,N,N,N,N,N,D,Int
Sun,N,C,D,N,N,N,N,C,Int
SGI,C,N,D,N,N,N,N,N,K
Apollo,N,N,C,N,N,N,N,D,Int
Red Hat,N,D,D,N,N,C,C,N,Int
Netscape,D,N,D,N,N,N,N,C,Doc
Internet Explorer,N,N,N,N,N,C,N,D,Doc
Firefox,C,C,N,N,N,C,N,N,Int
Chrome,D,C,N,N,C,N,N,C,Int
AOL,N,N,D,D,C,N,N,N,Int
Yahoo,C,N,D,N,N,N,N,N,Doc/Int
AltaVista/Excite/Lycos,D,N,D,N,N,N,N,N,Int
Google Search,D,N,D,N,N,N,N,C,Doc/Int
Baidu/Yandex/Naver/Seznam,D,N,N,N,N,N,N,N,Int
Bing,N,N,N,N,N,N,N,C,Int
Nokia,C,N,C,C,N,N,N,D,Int
RIM/BlackBerry,C,N,N,N,N,D,N,C,Int
Palm,D,N,D,N,N,N,N,N,Int
Windows Mobile/Phone,N,N,N,N,C,N,N,D,Int
Android,N,D,C,N,N,N,N,D,Int
Samsung,N,C,C,N,N,N,N,N,Int
Motorola,N,N,D,N,N,N,N,N,Int
Huawei/Xiaomi,N,N,C,N,N,N,N,N,regulation-driven
Arm,D,D,C,N,N,N,N,N,Int
TSMC,D,N,C,N,N,N,D,N,Doc/Int
Samsung Foundry,N,N,N,N,N,N,D,N,Int
GlobalFoundries,N,N,D,N,N,N,N,N,K
SMIC,N,N,N,N,N,N,N,N,regulation-driven
Nvidia,D,N,D,N,N,N,N,D,Int
Apple silicon,D,N,N,N,N,N,N,C,Int
Qualcomm,N,N,D,N,N,N,N,D,Int
AWS,D,N,D,N,N,N,C,C,Doc/Int
Microsoft Azure,N,N,C,N,N,N,N,D,Doc
Google Cloud,C,N,D,N,N,N,N,N,Int
Alibaba/Tencent/Huawei Cloud,N,N,N,N,N,N,N,N,regulation-driven
IBM Cloud,N,N,D,N,N,N,N,C,Int
Oracle Cloud,C,N,N,N,N,N,N,C,Int
Salesforce,D,N,N,C,N,N,N,N,K
OVHcloud,N,N,D,N,N,C,C,N,Int
T-Systems/Scaleway/IONOS,N,N,D,N,N,C,N,N,Int
VMware,N,N,D,N,N,N,N,D,Doc/Int
Rackspace/Helion/Verizon/Dell cloud,N,N,D,N,N,N,N,N,K
OpenAI,D,N,N,N,N,N,N,N,Int
Anthropic,D,N,N,N,N,C,C,N,Int
CoreWeave/Nebius/Crusoe/Lambda,C,N,C,N,N,N,N,N,Doc/Int
Itanium,N,N,N,N,N,N,N,D,Int
OS/2,N,N,C,N,N,N,N,D,Doc/Int
Cloudwatt/Numergy,N,N,D,N,N,N,N,N,K
Gaia-X,N/A,N/A,N/A,N/A,N/A,N/A,N/A,N/A,no market share
```

## Sources

1. [1 CLOUD SERVICES MARKET INVESTIGATION Summary of final decision 31 July 2025](https://assets.publishing.service.gov.uk/media/688b20e6ff8c05468cb7b120/summary_of_final_decision.pdf)
2. [IDC: PC Sales Rose 8.1 Percent in 2025, 9.6 Percent in Q4 - Thurrott.com](https://www.thurrott.com/hardware/331635/idc-pc-sales-rose-8-1-percent-in-2025-9-6-percent-in-q4)
3. [Gartner Says Worldwide PC Shipments Increased 9.3% in Fourth Quarter of 2025 and 9.1% for the Full Year](https://www.gartner.com/en/newsroom/press-releases/2026-1-20-gartner-says-worldwide-pc-shipments-increased-9-point-3-percent-in-fourth-quarter-of-2025-and-9-point-1-percent-for-the-full-year)
4. [AMD Hits Record x86 Market Share To Cut Into Intel's Chip Lead In Every Segment](https://hothardware.com/news/amd-record-x86-market-share-cut-intels-chip-lead)
5. [AMD Gains Ground as Intel x86 Market Share Goes Back to 1995 Levels](https://www.techpowerup.com/351908/amd-gains-ground-as-intel-x86-market-share-goes-back-to-1995-levels?cp=5)
6. [Search Engine Market Share by Country (August 2026)](https://www.searchengines.net/guides/search-engine-market-share-by-country/)
7. [Most Used Search Engine Statistics 2026: Market Share And User Preferences](https://fosspost.org/what-is-the-most-commonly-used-search-engine/)
8. [System Error: How the IBM Antitrust Suit Raised Computer Prices](https://www.cato.org/sites/cato.org/files/serials/files/regulation/1985/9/v9n5-6.pdf)
9. [15-292 History of Computing ! The 1960s and IBM’s Mainframe Computers IBM](https://www.cs.cmu.edu/~tcortina/15292s17/lectures/The1960sAndIBMsMainframeComputers.pdf)
10. [The Building of Big Blue](https://cs.stanford.edu/people/eroberts/cs181/projects/corporate-monopolies/development_ibm.html)
11. [IBM](https://en.wikipedia.org/wiki/IBM)
12. [International Business Machines Corporation (IBM)](https://www.ebsco.com/research-starters/business-and-management/international-business-machines-corporation-ibm/)
13. [2/11/20 1 15-292 History of Computing IBM Domination in the 1960s and 1970s IBM](https://www.cs.cmu.edu/~15292/assets/slides/08-IBMDominationInThe60s70s.pdf)
14. [The Antitrust Case, US v. IBM, is Tried and Eventually ...](https://www.historyofinformation.com/detail.php?id=923)
15. [DORA for ICT Third-Party Providers](https://dora-auditor.com/who-must-comply/ict-third-party-providers)
16. [BUNCH](https://en.wikipedia.org/wiki/BUNCH)
17. [INTERNATIONAL BUSINESS MACHINES CORP - Form 10-Q - FY1995](https://www.sec.gov/Archives/edgar/data/0000051143/000095011295002045/0000950112-95-002045.txt)
18. [INTERNATIONAL BUSINESS MACHINES CORP - Form 10-Q - FY1995](https://www.sec.gov/Archives/edgar/data/0000051143/000095011295002932/0000950112-95-002932.txt)
19. [January 1996](https://www.rtgsoftware.com/news/0196.htm)
20. [THE SELLING - OR NOT - OF WORDPERFECT](https://www.deseret.com/1996/2/4/19222840/the-selling-or-not-of-wordperfect/)
21. [JAMES F. RILL ASSISTANT ATTORNEY GENERAL PATRICIA A. SHAPIRO BRENT E. MARSHALL](https://www.justice.gov/atr/case-document/file/627986/dl)
22. [Largest 500 U.S. Companies by Market Cap in October 2026](https://www.finhacker.cz/en/largest-us-companies-by-market-cap/)
23. ["Competition is not working well," says UK CMA concluding cloud market investigation - DCD](https://www.datacenterdynamics.com/en/news/competition-is-not-working-well-says-uk-cma-concluding-cloud-market-investigation/)
24. [EU Aims DMA Gatekeeper Rules at AWS and Azure - webhosting.today](https://webhosting.today/2026/06/26/the-eu-just-aimed-its-gatekeeper-rules-at-aws-and-azure-for-the-first-time-and-it-used-ai-to-do-it/)
25. [ORACLE CORP - Form 10-K - FY2010](https://www.sec.gov/Archives/edgar/data/0001341439/000119312510151896/d10k.htm)
26. [Oracle Completes Sun Acquisition](https://www.eweek.com/news/oracle-completes-sun-acquisition/)
27. [Acquisition of Sun Microsystems by Oracle Corporation](https://en.wikipedia.org/wiki/Acquisition_of_Sun_Microsystems_by_Oracle_Corporation)
28. [Digital Equipment Corporation (DEC)](https://www.britannica.com/money/Digital-Equipment-Corporation)
29. [Lessons from Ken Olsen and Digital Equipment Corp.](https://sloanreview.mit.edu/article/lessons-from-ken-olsen-and-digital-equipment-corp/)
30. [What happened to Digital Equipment Corporation? - The Silicon Underground](https://dfarq.homeip.net/what-happened-to-digital-equipment-corporation/)
31. [Compaq to buy Digital Equipment Corp.](https://www.deseret.com/1998/1/26/19359987/compaq-to-buy-digital-equipment-corp/)
32. [DIGITAL EQUIPMENT CORP - Form 8-K - FY1998](https://www.sec.gov/Archives/edgar/data/0000028887/000095017298000075/0000950172-98-000075.txt)
33. [Digital Equipment Corporation](https://www.wabashtaxservice.com/dec.html)
34. [HEWLETT PACKARD CO - Form DFAN14A - FY2002](https://www.sec.gov/Archives/edgar/data/0000047217/000089161802000790/f77503h1dfan14a.htm)
35. [Compaq Agrees To Buy Digital \$9.6 Billion Deal Creates New Computer Powerhouse](https://www.spokesman.com/stories/1998/jan/27/compaq-agrees-to-buy-digital-96-billion-deal/)
36. [WANG LABS FILES FOR CHAPTER 11 - The Washington Post](https://www.washingtonpost.com/archive/business/1992/08/19/wang-labs-files-for-chapter-11/b48483fc-c8a1-472e-a632-621d2cc5f882/)
37. [Wang Laboratories emerges from Chapter 11 - UPI Archives](https://www.upi.com/Archives/1993/09/20/Wang-Laboratories-emerges-from-Chapter-11/2204748497600/)
38. [Wang Laboratories — Museum of the Fallen](https://museumofthefallen.org/companies/wang-laboratories/)
39. [archive.org](https://archive.org/download/Profileo1985/Profileo1985.asr.vtt)
40. [Commodore International](https://en.wikipedia.org/wiki/Commodore_International)
41. [Escom AG](https://en.wikipedia.org/wiki/Escom_AG)
42. [The rise and fall of Commodore](https://www.bcs.org/articles-opinion-and-research/the-rise-and-fall-of-commodore/)
43. [Lenovo buys IBM's PC unit for \$1.25 billion](https://www.chinadaily.com.cn/english/doc/2004-12/08/content_398336.htm)
44. [IBM sells PC business to China’s Lenovo for \$1.25 billion - MacDailyNews](https://macdailynews.com/2004/12/07/ibm_sells_pc_business_to_chinas_lenovo_for_125_billion/)
45. [The 20th Anniversary Of Lenovo-IBM Deal That Reshaped The PC Industry](https://www.forbes.com/sites/timbajarin/2025/05/06/the-20th-anniversary-of-lenovo-ibm-deal-that-reshaped-the-pc-industry/)
46. [HEWLETT PACKARD CO - Form 424B5 - FY2002](https://www.sec.gov/Archives/edgar/data/0000047217/000091205702025139/a2083027z424b5.txt)
47. [What Happened to Compaq: From PC Pioneer to HP Merger](https://tms-outsource.com/blog/posts/what-happened-to-compaq/)
48. [Intel sees record EU fine reduced further](https://www.northwestsignal.net/news/article_eb21de94-c9e6-5ca4-944f-b159f2ce895e.html)
49. [curia.europa.eu](https://curia.europa.eu/jcms/upload/docs/application/pdf/2025-12/cp250153en.pdf)
50. [Intel's EU court appeal against reduced €237m fine is published (correct\*)](https://www.mlex.com/mlex/articles/2470070/intel-s-eu-court-appeal-against-reduced-237m-fine-is-published-correct)
51. [AMD claws back ground against Intel in the CPU market, climbs to 35% share in desktop CPUs](https://www.tweaktown.com/news/113200/amd-claws-back-ground-against-intel-in-the-cpu-market-climbs-to-35-percent-share-in-desktop-cpus/index.html)
52. [AMD now ships more than 30% of x86 PC CPUs as Intel's long-held lead keeps shrinking](https://www.techspot.com/news/113569-amd-crosses-30-client-cpu-market-share-against.html)
53. [AMD reaches 46% of server x86 CPU revenue — Intel still controls 70% of the consumer PC market share](https://finance.yahoo.com/markets/stocks/articles/amd-reaches-46-server-x86-104000965.html)
54. [AMERICA ONLINE INC - Form 8-K - FY1998](https://www.sec.gov/Archives/edgar/data/0000883780/000088378098000052/0000883780-98-000052.txt/seq-3)
55. [Verizon completes its \$4.48 billion acquisition of Yahoo; Marissa Mayer leaves with \$23 million](https://www.cnbc.com/2017/06/13/verizon-completes-yahoo-acquisition-marissa-mayer-resigns.html)
56. [VERIZON COMMUNICATIONS INC - Form 10-Q - FY2017](https://www.sec.gov/Archives/edgar/data/0000732712/000119312517247167/d427004d10q.htm)
57. [Search Engine Statistics 2026: Market Share, Volume & AI - Colorlib](https://colorlib.com/wp/search-engine-statistics/)
58. [Search Engine Market Share 2026: Global Data Report](https://www.digitalapplied.com/blog/search-engine-market-share-2026-global-data)
59. [Search Engine Statistics 2026: Market Share, Volume & AI Shift • SQ Magazine](https://sqmagazine.co.uk/search-engine-statistics/)
60. [Search Engine Market Share by Country and Platform - Return On Now](https://returnonnow.com/resources/external-visibility/search-engine-market-share/)
61. [Final Prospectus](https://www.sec.gov/Archives/edgar/data/1288776/000119312504143377/d424b4.htm)
62. [Google's IPO: Grate Expectations (washingtonpost.com)](https://www.washingtonpost.com/wp-dyn/articles/A14939-2004Aug19.html)
63. [0% found this document useful (0 votes)](https://www.scribd.com/document/337967461/psd)
64. [Report: Nokia's smartphone market share dropping](https://www.fierce-network.com/wireless/report-nokia-s-smartphone-market-share-dropping)
65. [The Decline and Fall of Nokia — Grokipedia](https://grokipedia.com/page/The_Decline_and_Fall_of_Nokia)
66. [Smartphone Sales Up 24 Percent, iPhone's Share Nearly Doubled Last Year (Gartner)](https://techcrunch.com/2010/02/23/smartphone-iphone-sales-2009-gartner/)
67. [Nokia's Smartphone Collapse: The Fall of a Mobile Giant](https://www.stratrix.com/vault/nokia-smartphone-failure)
68. [Nokia completes sale of substantially all of its Devices & Services business to Microsoft](https://www.nokia.com/newsroom/nokia-completes-sale-of-substantially-all-of-its-devices--services-business-to-microsoft/)
69. [Microsoft to acquire Nokia’s devices & services business, license Nokia’s patents and mapping services - Source](https://news.microsoft.com/source/2013/09/03/microsoft-to-acquire-nokias-devices-services-business-license-nokias-patents-and-mapping-services/)
70. [PALM INC - Form DEFA14A - FY2010](https://www.sec.gov/Archives/edgar/data/0001100389/000119312510096841/dex991.htm)
71. [Global Foundry Revenue Approaches US\$53.49 Billion in 2Q26 as SMIC Narrows Market Share Gap with Samsung, Says TrendForce](https://www.trendforce.com/presscenter/news/20260909-13225.html)
72. [TSMC’s market share edges higher - Taipei Times](https://www.taipeitimes.com/News/biz/archives/2026/09/10/2003863979)
73. [Samsung Foundry drops further behind TSMC after disasterous Q4](https://www.phonearena.com/news/samsung-foundry-drops-further-behind-tsmc_id168447)
74. [Global Pure Foundry Market Share: Quarterly](https://counterpointresearch.com/en/insights/global-semiconductor-foundry-market-share)
75. [Largest Technology Companies by Market Cap in 2026](https://www.alpha-sense.com/largest-technology-companies-by-market-cap/)
76. [SMIC Foundry Market Share Hits 5.4% Without EUV, and Samsung Is Half a Point Ahead - Hardware Busters](https://hwbusters.com/news/smic-foundry-market-share-hits-5-4-without-euv-and-samsung-is-half-a-point-ahead/)
77. [Largest Companies by Market Cap in 2026: Nvidia Leads the Global Rankings](https://www.investingcube.com/deep-analysis/largest-companies-by-market-cap-in-2026-nvidia-leads-the-global-rankings/)
78. [The Largest Technology Companies by Market Cap in October 2026](https://www.fool.com/research/largest-tech-companies/)
79. [NVIDIA CORP - Form 10-Q - FY2025](https://www.sec.gov/Archives/edgar/data/1045810/000104581025000230/nvda-20251026.htm)
80. [China turns the screws on Nvidia with antitrust probe](https://www.theregister.com/on-prem/2025/09/15/china-turns-the-screws-on-nvidia-with-antitrust-probe/1479944)
81. [China rules Nvidia violated antitrust law in Mellanox case](https://www.calcalistech.com/ctechnews/article/9nkjvxdks)
82. [China Escalates Antitrust Probe into Nvidia Over Mellanox Deal - FintechMode](https://fintechmode.com/finance/china-samr-nvidia-mellanox-antitrust-probe/)
83. [ARM IPO: Everything you need to know about ARM - StoneX](https://www.stonex.com/en-gb/news-and-analysis/arm-ipo/)
84. [arm ipo strategy valuation](https://dc.fortune.com/2023/09/15/arm-ipo-strategy-valuation)
85. [Amazon Web Services (AWS) Statistics: Market Share & Competition Report 2026 - TechnologyChecker.io](https://technologychecker.io/blog/amazon-web-services-aws-statistics)
86. [Cloud Market Share 2026: AWS vs Azure vs Google Cloud](https://www.articsledge.com/post/cloud-market-share)
87. [Google Cloud Statistics: Market Share & Competition Report 2026 - TechnologyChecker.io](https://technologychecker.io/blog/google-cloud-statistics-report)
88. [Cloud Market Share Q2 2026: AWS vs Azure vs Google Cloud](https://codebasecoders.com/blog/cloud-market-share-q2-2026-aws-azure-google-cloud)
89. [amazon dominates the global cloud market in q2 2022](https://databoks.katadata.co.id/en/technology-telecommunications/statistics/84197f32ef88cec/amazon-dominates-the-global-cloud-market-in-q2-2022)
90. [2026 Q2 Global Cloud Market Share Report - Industry Report - 16IDC](https://www.16idc.com/en-us/article-detail/global-cloud-market-share-2026)
91. [Google Cloud's share hits record high of 15%, Amazon AWS drops to 28%](https://www.cloudtechdaily.com/en/articles/google-cloud-15-percent-share-aws-falls-2026)
92. [CMA Report: AWS and Microsoft Dominate UK + EEA Cloud Market in 2024](https://platformstack.io/posts/cma-report-aws-and-microsoft-dominate-uk-+-eea-cloud-market-in-2024/)
93. [CMA concludes UK cloud market investigation](https://datacentrereview.com/2025/08/aws-microsoft-to-face-competition-probe-as-cma-concludes-uk-cloud-market-investigation/)
94. [Cloud Computing Statistics 2026: Market, Growth & Costs](https://www.articsledge.com/post/cloud-computing-statistics)
95. [CISPE Challenges EU Commission’s Defence of Broadcom–VMware Merger](https://www.cispe.cloud/cispe-challenges-eu-commissions-defence-of-broadcom-vmware-merger/)
96. [reuters.com,2025:newsml L4N3TL1Z8:0 europe s cispe challenges broadcom s 69 billion vmware deal in eu court](https://br.tradingview.com/news/reuters.com,2025:newsml_L4N3TL1Z8:0-europe-s-cispe-challenges-broadcom-s-69-billion-vmware-deal-in-eu-court)
97. [VMWARE, INC. - Form DEF 14A - FY2023](https://www.sec.gov/Archives/edgar/data/1124610/000112461023000039/vmw-20230531.htm)
98. [Broadcom Completes \$69 Billion Acquisition of VMware on 22nd November 2023 after China Approval, \$61 Billion in Cash & \$8 Billion in Debt, Michael Dell to Receive \$20 Billion](https://www.caproasia.com/2023/11/25/broadcom-completes-69-billion-acquisition-of-vmware-on-22nd-november-2023-after-china-approval-61-billion-in-cash-8-billion-in-debt-michael-dell-to-receive-20-billion/)
99. [Broadcom Completes \$69 Billion Acquisition of VMware](https://www.compasslexecon.com/cases/broadcom-completes-69-billion-acquisition-of-vmware)
100. [EU cloud provider group files complaint over Broadcom’s VMware acquisition - SiliconANGLE](https://siliconangle.com/2025/07/24/eu-cloud-provider-group-files-complaint-broadcoms-vmware-acquisition/)
101. [CISPE Takes European Commission to Court to Annul Approval of Broadcom’s Acquisition of VMware](https://www.cispe.cloud/cispe-takes-european-commission-to-court-to-annul-approval-of-broadcoms-acquisition-of-vmware/)
102. [Justice Denied!?](https://www.cispe.cloud/justice-denied/)
103. [OpenAI funding: Every round, investor, and valuation (2026)](https://www.revenuememo.com/p/openai-funding)
104. [\$122B OpenAI, \$65B Anthropic — 2026 AI Rounds](https://valueaddvc.com/blog/biggest-ai-funding-rounds-of-2026-so-far-ranked)
105. [OpenAI is racing to raise \$30 billion before Anthropic's expected IPO](https://qz.com/openai-30-billion-funding-round-anthropic-ipo-102026)
106. [Racing to a Trillion: OpenAI and Anthropic's Funding History](https://pinggy.io/blog/openai_anthropic_funding_history/)
107. [OpenAI Seeks \$30 Bn Funding at \$1.4 Tn Valuation Ahead of Anthropic IPO: Report](https://analyticsindiamag.com/ai-news/openai-seeks-30-bn-funding-at-14-tn-valuation-ahead-of-anthropic-ipo-report)
108. [CoreWeave IPO](https://capital.com/en-int/learn/ipo/coreweave-ipo)
109. [CoreWeave prices IPO at \$40 a share, below expected range](https://www.cnbc.com/2025/03/27/coreweave-prices-ipo-at-40-a-share-below-expected-range.html)
110. [CoreWeave Announces Pricing of Initial Public Offering](https://www.coreweave.com/news/coreweave-announces-pricing-of-initial-public-offering)
111. [CoreWeave (CRWV) Q2 2026 Earnings Call Transcript](https://www.fool.com/earnings/call-transcripts/2026/08/18/coreweave-crwv-q2-2026-earnings-call-transcript/)
112. [Finsee on X: "\$CRWV Q2 2026 earnings: Hyper-Growth at a Heavy Cost CoreWeave's Q2 2026 results show a company scaling at an unprecedented pace, but it is paying a steep price to maintain its lead. Revenue accelerated to \$2.57 billion (+112% YoY). Backlog reached an astronomical \$104 billion. https://t.co/B7AOZvku6v" / X](https://x.com/Finsee_main/status/2087272998118027543)
113. [CoreWeave FY2026 Q2 Earnings: \$626M Loss, \$104B Backlog](https://beancount.io/blog/2026/09/22/coreweave-fy2026-q2-earnings-analysis)
114. [CoreWeave Q2 2026 Earnings: The \$104 Billion Backlog and the \$640 Million Interest Bill - Khan Capital](https://khancapitals.com/coreweave-q2-2026-earnings/)
115. [CoreWeave Q2 2026: \$129B Backlog Grew \$29.6B in Six Weeks Despite 50% Default Odds](https://www.techtimes.com/articles/324054/20260812/coreweave-q2-2026-129b-backlog-grew-296b-six-weeks-despite-50-default-odds.htm)
116. [CoreWeave Inc (CRWV) (Q2 2026) Earnings Call Highlights: Record Revenue and \$104 Billion ...](https://finance.yahoo.com/markets/stocks/articles/coreweave-inc-crwv-q2-2026-050033531.html)
117. [coreweave q4 earnings call highlights 030733529](https://finance.yahoo.com/news/coreweave-q4-earnings-call-highlights-030733529.html)
118. [Hyperscaler CapEx Hits \$690B in 2026](https://introl.com/blog/hyperscaler-capex-690-billion-microsoft-azure-power-bottleneck-2026)
119. [Hyperscaler AI Capex 2026: Four Spenders and a \$700 Billion-Plus Year](https://analysis-atlas.com/research/hyperscaler-ai-capex-2026/)
120. [Tech: Raising Hyperscaler Capex 2026 Estimates - CreditSights](https://know.creditsights.com/insights/tech-raising-hyperscaler-capex-2026-estimates/)
121. [Hyperscaler Capex 2026: \$720B–\$745B Guidance by Company](https://www.yieldtheory.app/research/hyperscaler-ai-capex-tracker-2026)
122. [Amazon, Meta and Microsoft face skeptical investors this week after Google report sparked sell-off](https://www.cnbc.com/2026/07/28/hyperscalers-face-higher-capex-scrutiny-after-alphabet-report-panned.html)
123. [Google's 90% Search Monopoly Faces DOJ Breakup \[2026\]](https://tech-insider.org/google-antitrust-appeal-doj-search-monopoly-2026/)
124. [US v. Google Antitrust Case: Ruling & Remedies Explained](https://thelawlion.com/cases/united-states-v-google)
125. [AWS, Microsoft Urged to Ease UK Cloud Services Barriers: Watchdog](https://www.globalbankingandfinance.com/aws-microsoft-address-cloud-services-barriers-uk-competition/)
126. [EU set to name AWS and Azure DMA gatekeepers in November](https://thenextweb.com/news/eu-set-to-name-aws-and-azure-dma-gatekeepers-in-november)
127. [DORA: What the List of Critical ICT Providers Means](https://swissgrc.com/en/dora-cloud-provider-supervisory-object/)
128. [October 2025 European Cloud Competition Observatory Third Report](https://www.cispe.cloud/website_cispe/wp-content/uploads/2025/10/ECCO-third-report-2025_10_29.pdf)
129. [Intel: General Court Confirms Previous Findings on the Merits but Reduces Fine](https://www.clearyantitrustwatch.com/2025/12/intel-general-court-confirms-previous-findings-on-the-merits-but-reduces-fine/)
130. [CMAs provisional findings on UK cloud services competition](https://www.boyesturner.com/insights/cmas-provisional-findings-regarding-cloud-services)
131. [Cloud services investigation: CMA’s findings mean for the cloud industry](https://www.civo.com/blog/cma-cloud-services-investigation-2025)
132. [remedies decision](https://www.congress.gov/crs_external_products/LSB/HTML/LSB11362.html)
133. [digital-strategy.ec.europa.eu](https://digital-strategy.ec.europa.eu/de/node/14973)
134. [Breaking: ESAs Publish First List of Critical ICT Third-Party Providers Under DORA](https://www.regulation-dora.eu/blog/esas-publish-critical-ict-third-party-providers-list-dora-2025)
135. [EU Court Reduces Intel’s Fine for “Naked Restrictions” in CPU Market](https://www.paulweiss.com/insights/client-memos/eu-court-reduces-intel-s-fine-for-naked-restrictions-in-cpu-market)
