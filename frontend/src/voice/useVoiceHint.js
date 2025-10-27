import { useState } from "react";
import { startAzureSTT } from "./azureClientSST";
import { fetchHint } from "../api/hintApi";

export function useVoiceHint({ apiBase, quizId }) {
    const [hint, setHint] = useState("");
    const [listening, setListening] = useState(false);

    async function startListening() {
        setListening(true);

        const { stop } = await startAzureSTT({
            apiBase,
            onFinal: async (text) => {
                const cleaned = text.toLowerCase().trim();
                if (cleaned.includes("dame una pista")) {
                    const h = await fetchHint(apiBase, quizId);
                    setHint(h);
                }
            },
            onError: (e) => console.error("Error STT:", e),
        });

        // Detener automáticamente tras 10 segundos
        setTimeout(() => {
            stop();
            setListening(false);
        }, 10000);
    }

    return { hint, listening, startListening };
}
