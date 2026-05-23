"""
⚠️ DEPRECATED: This script has been superseded by the citation_verifier/ package.

Use the new system instead:
    python main.py --file references.txt

This file is kept for backward compatibility only.
See README.md for migration instructions.
"""

import re
import requests
import time
from thefuzz import fuzz

# Dán danh sách tài liệu tham khảo của bạn vào đây
text_data = """
[1]. Dante AI. (2025, January 30). Rule-Based vs. AI Chatbot Buyers Guide: What Every Business Should Know. https://www.dante-ai.com/news/rule-based-vs-ai-chatbot-buyers-guide-what-every-business-should-know 
[2]. Lewis, P., Perez, E., Piktus, A., Petroni, F., Karpukhin, V., Goyal, N., ... & Kiela, D. (2020). Retrieval-Augmented Generation for Knowledge-Intensive NLP Tasks. Advances in Neural Information Processing Systems, 33, 9459-9474. https://doi.org/10.48550/arXiv.2005.11401
[3]. Johnson, J., Douze, M., & Jégou, H. (2019). Billion-scale similarity search with GPUs. IEEE Transactions on Big Data, 7(3), 535-547. https://doi.org/10.1109/TBDATA.2019.2921572
[4]. Berndt, Donald & Hevner, Alan & Studnicki, James. (2003). The Catch data warehouse: Support for community health care decision-making. Decision Support Systems. 35. 367-384. 10.1016/S0167-9236(02)00114-8.
[5]. Breiter, A., & Light, D. (2004). Decision support systems in schools—from data collection to decision making. In AMCIS 2004 Proceedings (p. 248). Association for Information Systems. https://aisel.aisnet.org/amcis2004/248
[6]. Charles, V., Rana, N. P., & Carter, L. (2022). Artificial intelligence for data-driven decision-making and governance in public affairs. Government Information Quarterly, 39(4), 101742. https://doi.org/10.1016/j.giq.2022.101742
[7]. Coralogix Team. (2023, October 24). How to train your own language model. Coralogix. https://coralogix.com/ai-blog/how-to-train-your-own-language-model/
[8]. Cui, Y., Che, W., Liu, T., Qin, B., & Yang, Z. (2021). Pre-training with whole word masking for Chinese BERT. IEEE/ACM Transactions on Audio, Speech, and Language Processing, 29, 3504–3514. https://doi.org/10.1109/TASLP.2021.3120580
[9]. Cui, Y., Che, W., Liu, T., Qin, B., Wang, S., & Hu, G. (2020). Revisiting pre-trained models for Chinese natural language processing. arXiv preprint arXiv:2004.13922. https://doi.org/10.48550/arXiv.2004.13922
[10]. Devlin, J., Chang, M.-W., Lee, K., & Toutanova, K. (2019). BERT: Pre-training of deep bidirectional transformers for language understanding. In Proceedings of the 2019 Conference of the North American Chapter of the Association for Computational Linguistics (pp. 4171–4186). https://doi.org/10.18653/v1/N19-1423
[11]. Hien, B. N., Tuyen, N. T. K., Lan, N. T., Ngan, N. T. K., & Thanh, N. N. (2024). The impact of digital government initiatives on public value creation: Evidence from Ho Chi Minh City–Vietnam. Revista de Gestão Social e Ambiental, 18(2), 1–23. https://doi.org/10.24857/rgsa.v18n2-001
[12]. Himeur, Y., Elnour, M., Fadli, F., Meskin, N., Petri, I., Rezgui, Y., Bensaali, F., & Amira, A. (2023). AI-based anomaly detection: Challenges and solutions in real-world applications. In 2023 International Conference on Innovations in Intelligent Systems and Applications (IRASET) (pp. 1–7). IEEE. https://doi.org/10.1109/IRASET57153.2023.10153005
[13]. Touvron, H., Lavril, T., Izacard, G., Martinet, X., Lachaux, M. A., Lacroix, T., ... & Lample, G. (2023). LLaMA: Open and Efficient Foundation Language Models. arXiv preprint arXiv:2302.13971. https://doi.org/10.48550/arXiv.2302.13971
[14]. Hossin, M. A., Du, J., Mu, L., & Asante, I. O. (2023). Big data-driven public policy decisions: Transformation toward smart governance. SAGE Open, 13(4). https://doi.org/10.1177/21582440231215123
[15]. Huang, L. (2023, July 11). Retrieval augmented generation (RAG). Medium. https://medium.com/@linghuang_76674/retrieval-augmented-generation-rag-3f492cfb6923
[16]. Reimers, N., & Gurevych, I. (2019). Sentence-BERT: Sentence Embeddings using Siamese BERT-Networks. Proceedings of the 2019 Conference on Empirical Methods in Natural Language Processing, 3982-3992. https://doi.org/10.18653/v1/D19-1410
[17]. Gao, Y., Xiong, Y., Gao, X., Jia, K., Pan, J., Bi, Y., ... & Wang, H. (2023). Retrieval-Augmented Generation for Large Language Models: A Survey. arXiv preprint arXiv:2312.10997. https://doi.org/10.48550/arXiv.2312.10997
[18]. Jiang, A. Q., Sablayrolles, A., Mensch, A., Bamford, C., Chaplot, D. S., Casas, D. D. L., ... & Sayed, W. E. (2023). Mistral 7B. arXiv preprint arXiv:2310.06825. https://doi.org/10.48550/arXiv.2310.06825
[19]. Ram, O., Levine, Y., Dalmedigo, I., Muhlgay, D., Shashua, A., Leyvand, E., & Shoham, Y. (2023). In-Context Retrieval-Augmented Language Models. Transactions of the Association for Computational Linguistics, 11, 1316-1331. https://doi.org/10.1162/tacl_a_00589
[20]. Asai, A., Zhong, Z., Chen, D., Koh, P. W., Zettlemoyer, L., Hajishirzi, H., & Yih, W. T. (2023). Self-RAG: Learning to Retrieve, Generate, and Critique through Self-Reflection. arXiv preprint arXiv:2310.11511. https://doi.org/10.48550/arXiv.2310.11511
[21]. Lorica, B. (2023, March 14). Maximizing the potential of large language models. Gradient Flow. https://gradientflow.com/maximizing-the-potential-of-large-language-models/
[22]. Karpukhin, V., Oguz, B., Min, S., Lewis, P., Wu, L., Edunov, S., ... & Yih, W. T. (2020). Dense Passage Retrieval for Open-Domain Question Answering. Proceedings of the 2020 Conference on Empirical Methods in Natural Language Processing, 6769-6781. https://doi.org/10.18653/v1/2020.emnlp-main.550
[23]. Khattab, O., & Zaharia, M. (2020). ColBERT: Efficient and Effective Passage Search via Contextualized Late Interaction over BERT. Proceedings of the 43rd International ACM SIGIR Conference on Research and Development in Information Retrieval, 39-48. https://doi.org/10.1145/3397271.3401075
[24]. Borgeaud, S., Mensch, A., Hoffmann, J., Cai, T., Rutherford, E., Millican, K., ... & Sifre, L. (2022). Improving language models by retrieving from trillions of tokens. International Conference on Machine Learning, 2206-2240. https://doi.org/10.48550/arXiv.2112.04426
[25]. Wei, J., Wang, X., Schuurmans, D., Bosma, M., Xia, F., Chi, E., ... & Zhou, D. (2022). Chain-of-Thought Prompting Elicits Reasoning in Large Language Models. Advances in Neural Information Processing Systems, 35, 24824-24837. https://doi.org/10.48550/arXiv.2201.11903
[26]. Nguyen, D. Q., & Nguyen, A. T. (2020). PhoBERT: Pre-trained language models for Vietnamese. arXiv preprint arXiv:2003.00744. https://doi.org/10.48550/arXiv.2003.00744
[27]. Nguyen, D. Q., Vu, T., & Nguyen, A. T. (2020). BERTweet: A pre-trained language model for English Tweets. arXiv preprint arXiv:2005.10200. https://doi.org/10.48550/arXiv.2005.10200
[28]. Ouyang, L., Wu, J., Jiang, X., Almeida, D., Wainwright, C., Mishkin, P., ... & Lowe, R. (2022). Training language models to follow instructions with human feedback. Advances in Neural Information Processing Systems, 35, 27730-27744. https://doi.org/10.48550/arXiv.2203.02155
[29]. Min, S., Krishna, K., Lyu, X., Lewis, M., Yih, W. T., Koh, P. W., ... & Zettlemoyer, L. (2023). FActScore: Fine-grained Atomic Evaluation of Factual Precision in LLM Generation. Proceedings of the 2023 Conference on Empirical Methods in Natural Language Processing, 12076-12100. https://doi.org/10.18653/v1/2023.emnlp-main.741
[30]. Parycek, P., & Sachs, M. (Eds.). (2020). CeDEM Asia 2020: Proceedings of the International Conference for E-Democracy and Open Government, Asia 2020. Edition Donau-Universität Krems.
[31]. Poudel, N. (2024). The impact of big data-driven artificial intelligence systems on public service delivery in cloud-oriented government infrastructures. Journal of Artificial Intelligence and Machine Learning in Cloud Computing Systems, 8(11), 13–25. https://www.scipublications.org/index.php/jaimlccs/article/view/1047
[32]. Ribeiro, M. T., Singh, S., & Guestrin, C. (2016). “Why should I trust you?”: Explaining the predictions of any classifier. In Proceedings of the 22nd ACM SIGKDD International Conference on Knowledge Discovery and Data Mining (pp. 1135–1144). ACM. https://doi.org/10.1145/2939672.2939778
[33]. The Pickl.ai Team. (2023, May 9). Information retrieval in NLP: Understanding the basics and its importance. Pickl.ai. https://www.pickl.ai/blog/information-retrieval-in-nlp/
[34]. Tkemaladze, J. (2024). The concept of data-driven automated governance. Georgian Scientists, 6(4), 399–410. https://doi.org/10.52340/gs.2024.06.04.40
[35]. Hu, E. J., Shen, Y., Wallis, P., Allen-Zhu, Z., Li, Y., Wang, S., ... & Chen, W. (2021). LoRA: Low-Rank Adaptation of Large Language Models. arXiv preprint arXiv:2106.09685. https://doi.org/10.48550/arXiv.2106.09685
[36]. Tran, K. (2020). From English to foreign languages: Transferring pre-trained language models. arXiv preprint arXiv:2002.07306. https://doi.org/10.48550/arXiv.2002.07306
[37]. Dettmers, T., Pagnoni, A., Holtzman, A., & Zettlemoyer, L. (2023). QLoRA: Efficient Finetuning of Quantized LLMs. Advances in Neural Information Processing Systems, 36, 10088-10115. https://doi.org/10.48550/arXiv.2305.14314
[38]. Scao, T. L., Fan, A., Akiki, C., Pavlick, E., Ilić, S., Hesslow, D., ... & Wolf, T. (2022). BLOOM: A 176B-Parameter Open-Access Multilingual Language Model. arXiv preprint arXiv:2211.05100. https://doi.org/10.48550/arXiv.2211.05100
[39]. Vaswani, A., Shazeer, N., Parmar, N., Uszkoreit, J., Jones, L., Gomez, A. N., Kaiser, Ł., & Polosukhin, I. (2017). Attention is all you need. In Advances in Neural Information Processing Systems 30 (NIPS 2017) (pp. 5998–6008). https://papers.nips.cc/paper/2017/file/3f5ee243547dee91fbd053c1c4a845aa-Paper.pdf
[40]. Wang, H., Li, J., Wu, H., Hovy, E., & Sun, Y. (2023). Pre-trained language models and their applications. Engineering, 25, 51–65. https://doi.org/10.1016/j.eng.2022.04.024

"""

def cross_check_citations_v2(text):
    # Regex cơ bản lấy mã DOI
    raw_doi_pattern = re.compile(r'10\.\d{4,9}/[-._;()/:A-Z0-9]+', re.IGNORECASE)
    raw_dois = raw_doi_pattern.findall(text)
    
    # Làm sạch: Cắt bỏ các dấu chấm, phẩy dư thừa ở cuối chuỗi
    clean_dois = list(set([doi.rstrip('.,;') for doi in raw_dois]))
    
    print(f"🔍 Đã quét và làm sạch được {len(clean_dois)} mã DOI. Bắt đầu đối chiếu chéo...\n")
    print("-" * 70)

    for doi in clean_dois:
        # 1. Phân luồng API dựa trên nguồn gốc DOI
        if 'arxiv' in doi.lower():
            # arXiv sử dụng DataCite API
            url = f"https://api.datacite.org/dois/{doi}"
            api_source = "DataCite"
        else:
            # Các tạp chí/hội nghị thông thường dùng Crossref API
            url = f"https://api.crossref.org/works/{doi}"
            api_source = "Crossref"
            
        headers = {'User-Agent': 'DOICheckerScript/2.0 (mailto:admin@example.com)'}
        
        try:
            response = requests.get(url, headers=headers, timeout=10)
            
            if response.status_code == 200:
                data = response.json()
                official_title = ""
                
                # 2. Bóc tách tên bài báo tùy theo cấu trúc JSON của từng API
                if api_source == "Crossref":
                    title_list = data['message'].get('title', [])
                    if title_list:
                        official_title = title_list[0]
                elif api_source == "DataCite":
                    try:
                        official_title = data['data']['attributes']['titles'][0]['title']
                    except (KeyError, IndexError):
                        pass
                
                if not official_title:
                    print(f"⚠️ [THIẾU DATA] DOI: {doi} (Tồn tại nhưng API không trả về tên bài báo)")
                    continue
                    
                # 3. So khớp mờ
                match_score = fuzz.partial_ratio(official_title.lower(), text.lower())
                
                if match_score >= 85:
                    print(f"✅ [AN TOÀN - Khớp {match_score}%]")
                    print(f"   DOI: {doi}")
                    print(f"   Nguồn: {api_source}")
                    print(f"   Tên API: {official_title}\n")
                else:
                    print(f"❌ [CẢNH BÁO SAI LỆCH - Khớp {match_score}%]")
                    print(f"   DOI: {doi}")
                    print(f"   Nguồn: {api_source}")
                    print(f"   Tên API báo về: {official_title}")
                    print(f"   -> Cần kiểm tra lại trích dẫn này!\n")
                    
            elif response.status_code == 404:
                print(f"💀 [MÃ DOI ẢO/DEAD LINK] {doi} (Nguồn tra cứu: {api_source})\n")
            else:
                print(f"⚠️ [LỖI API {response.status_code}] {doi}\n")
                
        except requests.exceptions.RequestException as e:
            print(f"🔌 [LỖI KẾT NỐI] {doi} - {str(e)}\n")
            
        # Delay để tôn trọng rate limit của các API
        time.sleep(0.5)

if __name__ == "__main__":
    cross_check_citations_v2(text_data)