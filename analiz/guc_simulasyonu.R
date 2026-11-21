# Güç simülasyonu (tasarım belgesi, Bölüm 10; ön kayıt: https://osf.io/y45rq)
#
# Soru: 60 soru × 2 tekrarlık tasarım, doğrulayıcı hipotezlerdeki (H1–H3) etkileri yakalamaya
# yetiyor mu? Ana deneyle aynı yapıda sahte veri üretilir, ön kayıttaki modeller aynen kurulur,
# Holm düzeltmesi uygulanır ve etkinin kaç simülasyonda yakalandığı sayılır.
#
# Gerçek deney verisi kullanılmaz; API çağrısı yapılmaz.
#
# Çalıştırma:  Rscript analiz/guc_simulasyonu.R            (her senaryoda 500 simülasyon)
#              Rscript analiz/guc_simulasyonu.R 20         (hızlı deneme: 20 simülasyon)

suppressPackageStartupMessages({
  library(lme4)
  library(parallel)
})

TOHUM <- 20261122
N_SIM <- if (length(commandArgs(TRUE)) >= 1) as.integer(commandArgs(TRUE)[1]) else 500
ISCI <- max(1, detectCores() %/% 2)
CIKTI <- file.path("analiz", "sonuclar", "guc_simulasyonu.csv")

# --- Varsayımlar ---------------------------------------------------------------------------
SORU_SD <- 1.0                                    # sorular arası fark (logit ölçeğinde SS)
MODEL_ETKISI <- c(deepseek = 0, qwen = 0.5, gemma = -0.5)
# Taban oran: tipik bir soruda (soru etkisi 0), ortalama modelde, k = 3, küçük hata, Türkçe, açık.
TABAN_ORANLARI <- c(0.02, 0.05, 0.20, 0.40)
ETKILER <- list(                                  # odds oranları
  orta  = c(k = 1.20, buyuk_hata = 0.67, muttefik = 0.67),
  kucuk = c(k = 1.10, buyuk_hata = 0.80, muttefik = 0.80),
  sifir = c(k = 1.00, buyuk_hata = 1.00, muttefik = 1.00)  # doğrulama: yanlış alarm oranı ~%5 olmalı
)

senaryolar <- rbind(
  expand.grid(taban = TABAN_ORANLARI, etki = c("orta", "kucuk"), stringsAsFactors = FALSE),
  data.frame(taban = 0.20, etki = "sifir")
)

# --- Tasarım (Bölüm 7: her koşulda 60 soru × 2 tekrar × 3 model) -----------------------------
SORULAR <- 1:60
TUR <- rep(c("cizgi", "bilgi", "aritmetik"), each = 20)
K_GRUP <- c(1, 2, 3, 5)

a_normal <- expand.grid(soru = SORULAR, tekrar = 1:2, model = names(MODEL_ETKISI), k = K_GRUP,
                        hata = c("kucuk", "buyuk"), dil = c("tr", "en"),
                        gorunurluk = c("acik", "gizli"), stringsAsFactors = FALSE)
a_normal$muttefik <- 0
a_muttefik <- expand.grid(soru = SORULAR, tekrar = 1:2, model = names(MODEL_ETKISI), k = K_GRUP,
                          konum = c("basta", "sonda"), stringsAsFactors = FALSE)
a_muttefik$hata <- "kucuk"
a_muttefik$dil <- "tr"
a_muttefik$gorunurluk <- "acik"
a_muttefik$muttefik <- 1
stopifnot(nrow(a_normal) == 11520, nrow(a_muttefik) == 2880)   # Bölüm 7 tablosu

faktorle <- function(d) {
  d$tur <- factor(TUR[d$soru], levels = c("cizgi", "bilgi", "aritmetik"))
  d$soru <- factor(d$soru)
  d$model <- factor(d$model, levels = names(MODEL_ETKISI))
  d$hata <- factor(d$hata, levels = c("kucuk", "buyuk"))
  d$dil <- factor(d$dil, levels = c("tr", "en"))
  d$gorunurluk <- factor(d$gorunurluk, levels = c("acik", "gizli"))
  d
}

# lme4'ün varsayılan ayarı (bobyqa + Nelder_Mead). Ön kayıt ayar belirtmediği için paketin
# varsayılanı kullanılır; ana analizde de aynısı kullanılacak. (Denendi: "nloptwrap" aynı tahminleri
# verip yanlış yakınsama uyarıları üretiyor; "bobyqa" ile varsayılan arasında fark yok.)
KONTROL <- glmerControl()

wald <- function(model, katsayi) {
  s <- summary(model)$coefficients
  c(tahmin = s[katsayi, "Estimate"], p = s[katsayi, "Pr(>|z|)"])
}

kur <- function(formul, veri) {
  uyari <- FALSE
  model <- withCallingHandlers(
    tryCatch(glmer(formul, veri, family = binomial, control = KONTROL), error = function(e) NULL),
    warning = function(w) {
      uyari <<- TRUE
      invokeRestart("muffleWarning")
    })
  list(model = model, uyari = uyari || (!is.null(model) && isSingular(model)))
}

bir_simulasyon <- function(i, taban, etki) {
  set.seed(TOHUM + i)   # her simülasyon kendi tohumuyla: sonuç işçi sayısından bağımsız
  b <- log(etki)
  soru_etkisi <- rnorm(length(SORULAR), 0, SORU_SD)
  uret <- function(d) {
    eta <- qlogis(taban) + b[["k"]] * (d$k - 3) + b[["buyuk_hata"]] * (d$hata == "buyuk") +
      b[["muttefik"]] * d$muttefik + MODEL_ETKISI[d$model] + soru_etkisi[d$soru]
    d$uydu <- rbinom(nrow(d), 1, plogis(eta))
    faktorle(d)
  }
  normal <- uret(a_normal)
  muttefik <- uret(a_muttefik)

  # H1 ve H2 (Bölüm 10)
  h12 <- kur(uydu ~ k + hata + dil + gorunurluk + model + tur + (1 | soru), normal)
  # H3: A: Müttefik + eşleşen A: Normal koşulları (Türkçe, küçük, açık, k = 1–5)
  eslesen <- normal[normal$dil == "tr" & normal$hata == "kucuk" & normal$gorunurluk == "acik", ]
  ortak <- setdiff(names(muttefik), "konum")
  h3 <- kur(uydu ~ muttefik + k + model + tur + (1 | soru), rbind(eslesen[, ortak], muttefik[, ortak]))

  bos <- c(tahmin = NA, p = NA)   # model kurulamazsa: etki yakalanamadı sayılır
  sonuc <- rbind(
    H1 = if (is.null(h12$model)) bos else wald(h12$model, "k"),
    H2 = if (is.null(h12$model)) bos else wald(h12$model, "hatabuyuk"),
    H3 = if (is.null(h3$model)) bos else wald(h3$model, "muttefik"))
  p_holm <- p.adjust(sonuc[, "p"], method = "holm")
  yon <- c(H1 = 1, H2 = -1, H3 = -1)
  yakalandi <- !is.na(p_holm) & p_holm < 0.05 & sign(sonuc[, "tahmin"]) == yon
  c(yakalandi, tahmin = sonuc[, "tahmin"], uyari_h12 = h12$uyari, uyari_h3 = h3$uyari,
    uyma = mean(normal$uydu))
}

main <- function() {
  cat(sprintf("Güç simülasyonu: %d senaryo × %d simülasyon, %d işçi\n\n",
              nrow(senaryolar), N_SIM, ISCI))
  kume <- makeCluster(ISCI)
  on.exit(stopCluster(kume))
  clusterEvalQ(kume, suppressPackageStartupMessages(library(lme4)))
  clusterExport(kume, c("TOHUM", "SORULAR", "TUR", "MODEL_ETKISI", "SORU_SD", "a_normal",
                        "a_muttefik", "faktorle", "KONTROL", "wald", "kur", "bir_simulasyon"))
  satirlar <- list()
  for (s in seq_len(nrow(senaryolar))) {
    taban <- senaryolar$taban[s]
    etki_adi <- senaryolar$etki[s]
    etki <- ETKILER[[etki_adi]]
    sure <- system.time(
      r <- do.call(rbind, parLapply(kume, s * 100000 + seq_len(N_SIM), bir_simulasyon, taban, etki))
    )[["elapsed"]]
    guc <- colMeans(r[, c("H1", "H2", "H3"), drop = FALSE])
    satirlar[[s]] <- data.frame(
      etki = etki_adi, taban = taban, uyma_orani = mean(r[, "uyma"]),
      guc_H1 = guc[["H1"]], guc_H2 = guc[["H2"]], guc_H3 = guc[["H3"]],
      tahmin_H1 = mean(r[, "tahmin.H1"], na.rm = TRUE), gercek_H1 = log(etki[["k"]]),
      tahmin_H2 = mean(r[, "tahmin.H2"], na.rm = TRUE), gercek_H2 = log(etki[["buyuk_hata"]]),
      tahmin_H3 = mean(r[, "tahmin.H3"], na.rm = TRUE), gercek_H3 = log(etki[["muttefik"]]),
      uyarili_kurulum = mean(r[, "uyari_h12"] | r[, "uyari_h3"]), n_sim = N_SIM, sure_sn = sure)
    with(satirlar[[s]], cat(sprintf(
      "%-6s taban %%%-3.0f (uyma %%%4.1f) | güç H1 %%%3.0f  H2 %%%3.0f  H3 %%%3.0f | uyarı %%%2.0f | %4.0f sn\n",
      etki, 100 * taban, 100 * uyma_orani, 100 * guc_H1, 100 * guc_H2, 100 * guc_H3,
      100 * uyarili_kurulum, sure_sn)))
  }
  tablo <- do.call(rbind, satirlar)
  dir.create(dirname(CIKTI), showWarnings = FALSE, recursive = TRUE)
  write.csv(tablo, CIKTI, row.names = FALSE)
  cat("\nTahmin doğrulaması (ortalama tahmin / gerçek değer, log-odds):\n")
  print(format(tablo[, c("etki", "taban", "tahmin_H1", "gercek_H1", "tahmin_H2", "gercek_H2",
                         "tahmin_H3", "gercek_H3")], digits = 3), row.names = FALSE)
  cat(sprintf("\nMonte Carlo hatası: güç %%80 iken ± %%%.1f (%d simülasyon)\n",
              100 * 1.96 * sqrt(0.8 * 0.2 / N_SIM), N_SIM))
  cat("Sonuçlar:", CIKTI, "\n")
}

main()
