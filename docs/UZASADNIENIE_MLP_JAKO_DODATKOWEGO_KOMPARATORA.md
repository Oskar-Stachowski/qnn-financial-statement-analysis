# Uzasadnienie dodatkowego refinementu MLP jako komparatora dla QNN

## Decyzja metodologiczna

Pierwotna, zamrożona reguła warunkowego refinementu wskazała trzy rodziny modeli: XGBoost, HistGradientBoosting oraz Random Forest. Reguła ta pozostaje bez zmian i nadal wyznacza główny tor selekcji modeli klasycznych. PyTorch MLP nie jest dopisywany do tej grupy ani nie może wpłynąć na główny ranking lub wybór globalnego zwycięzcy.

Przed rozpoczęciem refinementu oraz eksperymentu QNN wprowadzono natomiast osobny, wtórny tor badawczy: refinement MLP jako bezpośredniego komparatora architektonicznego dla hybrydowej kwantowej sieci neuronowej. Decyzja wynika z tytułu i celu pracy — porównanie QNN wyłącznie z modelami drzewiastymi lub liniowymi nie odpowiada w pełni na pytanie, czy obserwowany wynik jest związany z częścią kwantową, czy ogólnie z użyciem modelu neuronowego.

## Zakres dodatkowego eksperymentu

Dodatkowy refinement obejmuje wyłącznie osiem konfiguracji MLP, które były już zapisane w zamrożonym rejestrze kandydatów. Nie dodano nowych wartości hiperparametrów po zapoznaniu się z wynikami coarse searchu. Eksperyment jest wykonywany na bloku `L+D`, ponieważ był to najlepszy blok MLP w coarse searchu. Zastosowano ten sam seed bazowy, te same sześć foldów czasowych, ten sam preprocessing oraz tę samą główną metrykę PR-AUC.

Najlepszy kandydat MLP z połączonej puli coarse i dodatkowego refinementu jest następnie oceniany dla dwóch dodatkowych seedów. Wynik końcowy powstaje przez uśrednienie surowych score'ów dla trzech seedów i jednorazowe wyznaczenie pooled OOF PR-AUC, analogicznie do modeli QNN.

## Status analizy i ograniczenia wnioskowania

Dodatkowy tor MLP ma status analizy wtórnej, zadeklarowanej po poznaniu wyników coarse searchu, lecz przed wynikami refinementu i QNN. Z tego względu:

1. nie zmienia pierwotnego protokołu selekcji modeli klasycznych;
2. nie może zmienić głównego globalnego zwycięzcy;
3. jest przedstawiany w oddzielnej tabeli refined MLP vs QNN;
4. służy ocenie porównawczej, a nie „ratowaniu” wyniku MLP;
5. nie uzasadnia twierdzenia o przewadze kwantowej, zwłaszcza że QNN działa na symulatorze analitycznym.

Zarówno przewaga MLP, przewaga QNN, jak i brak istotnej różnicy są pełnoprawnymi wynikami naukowymi. Wniosek powinien uwzględniać nie tylko wartość punktową PR-AUC i ROC-AUC, lecz także stabilność między foldami i seedami, koszt obliczeniowy, różnicę reprezentacji wejściowej oraz niepewność oszacowania.

Porównanie refined MLP z QNN nie jest samo w sobie eksperymentem izolującym „efekt kwantowy”, ponieważ QNN korzysta z reprezentacji PCA ograniczonej do 4 lub 6 komponentów, a główny MLP wykorzystuje pełny zamrożony blok cech. Dlatego po wyborze finalnego QNN należy dodatkowo wykonać diagnostyczny MLP na dokładnie tej samej reprezentacji PCA. Taki PCA-matched control służy ocenie wpływu reprezentacji, ale nie zmienia rankingu głównego ani wyboru konfiguracji.

## Fragment do wykorzystania w pracy

W celu zapewnienia bezpośredniego komparatora architektonicznego dla modelu QNN przeprowadzono dodatkowy refinement klasycznej sieci MLP. Rozszerzenie to nie modyfikowało zamrożonej reguły warunkowego refinementu ani głównego rankingu modeli klasycznych. Miało ono charakter wtórnej analizy porównawczej, zadeklarowanej po coarse searchu, lecz przed wykonaniem refinementu i eksperymentów QNN. Zakres ograniczono do ośmiu konfiguracji MLP uprzednio zapisanych w rejestrze kandydatów oraz do bloku `L+D`, który uzyskał najlepszy wynik MLP w coarse searchu. Najlepszy kandydat został następnie potwierdzony dla dwóch dodatkowych seedów, a wynik zagregowano na podstawie średniej surowych score'ów. Takie rozdzielenie pozwala zestawić klasyczną i kwantową architekturę neuronową, jednocześnie nie naruszając pierwotnego protokołu selekcji modeli.

## Odpowiedź dla recenzenta

Dodatkowy refinement MLP nie został przedstawiony jako element pierwotnej, potwierdzającej selekcji modeli klasycznych. Jest jawnie oznaczony jako analiza wtórna, motywowana zgodnością z problemem badawczym i tytułem pracy. Zastosowano wyłącznie wcześniej prerejestrowane konfiguracje, nie wykorzystano danych chronionych ani wyników QNN, a dodatkowy MLP nie może zmienić głównego zwycięzcy. Dzięki temu rozszerzenie zwiększa wartość interpretacyjną porównania, nie ukrywając jego post-coarse charakteru.
