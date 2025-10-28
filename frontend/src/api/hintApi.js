// /api/hint.js
export default async function handler(req, res) {
    const { prompt } = req.body;
    try {
        const r = await fetch("https://api.perplexity.ai/chat/completions", {
            method: "POST",
            headers: {
                "Authorization": `Bearer ${process.env.PERPLEXITY_API_KEY}`,
                "Content-Type": "application/json",
            },
            body: JSON.stringify({
                model: "pplx-70b-online",  // o pplx-70b-instruct si prefieres sin browsing
                messages: [
                    { role: "system", content: "Eres un asistente que da pistas sin revelar respuestas." },
                    { role: "user", content: prompt }
                ],
            }),
        });

        const data = await r.json();
        const text = data.choices?.[0]?.message?.content || "No se generó pista.";
        res.status(200).json({ hint: text });
    } catch (err) {
        console.error(err);
        res.status(500).json({ error: "Error generando pista" });
    }
}
